import { spawn, ChildProcess } from "child_process";
import { EventEmitter } from "events";
import { RelicConfig } from "./config";

export class McpClientManager extends EventEmitter {
  private process: ChildProcess | null = null;
  private config: RelicConfig;
  private requestId = 0;
  private pendingRequests = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();
  private outputBuffer = "";
  private _isRunning = false;

  constructor(config: RelicConfig) {
    super();
    this.config = config;
  }

  async start(): Promise<void> {
    if (this._isRunning) return;

    return new Promise((resolve, reject) => {
      const args = [
        "serve",
        this.config.repoPath,
        "--mock",
        ...(this.config.useMockData ? [] : ["--no-mock"]),
      ];

      this.process = spawn(this.config.enginePath, args, {
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, PYTHONPATH: "" },
      });

      this.process.stdout?.on("data", (data: Buffer) => {
        this.handleData(data.toString());
      });

      this.process.stderr?.on("data", (data: Buffer) => {
        console.error("[relic-engine stderr]", data.toString());
      });

      this.process.on("error", (err) => {
        console.error("[relic-engine error]", err);
        this._isRunning = false;
        reject(err);
      });

      this.process.on("exit", (code) => {
        this._isRunning = false;
        if (code !== 0) {
          console.warn(`[relic-engine exited with code ${code}]`);
        }
      });

      this._isRunning = true;
      resolve();
    });
  }

  stop(): void {
    this.process?.kill();
    this._isRunning = false;
  }

  private handleData(data: string): void {
    this.outputBuffer += data;

    let newlineIdx: number;
    while ((newlineIdx = this.outputBuffer.indexOf("\n")) !== -1) {
      const line = this.outputBuffer.slice(0, newlineIdx).trim();
      this.outputBuffer = this.outputBuffer.slice(newlineIdx + 1);

      if (!line) continue;

      try {
        const msg = JSON.parse(line);
        if (msg.id && this.pendingRequests.has(msg.id)) {
          const { resolve, reject } = this.pendingRequests.get(msg.id)!;
          this.pendingRequests.delete(msg.id);
          if (msg.error) {
            reject(new Error(JSON.stringify(msg.error)));
          } else {
            resolve(msg.result || msg);
          }
        } else if (msg.jsonrpc === "2.0" && msg.result !== undefined) {
          const id = msg.id as number;
          if (this.pendingRequests.has(id)) {
            const { resolve } = this.pendingRequests.get(id)!;
            this.pendingRequests.delete(id);
            resolve(msg.result);
          }
        }
      } catch {
        // Not a JSON line, ignore
      }
    }
  }

  async ensureParsed(repoPath: string): Promise<void> {
    return Promise.resolve();
  }

  async callTool(toolName: string, args: Record<string, unknown>): Promise<unknown> {
    if (!this._isRunning || !this.process) {
      throw new Error("MCP server not running");
    }

    const id = ++this.requestId;

    const request = {
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: {
        name: toolName,
        arguments: args,
      },
    };

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });

      const msg = JSON.stringify(request) + "\n";
      this.process!.stdin?.write(msg, (err) => {
        if (err) {
          this.pendingRequests.delete(id);
          reject(err);
        }
      });

      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`Request ${id} timed out`));
        }
      }, 15000);
    });
  }

  async getContextSummary(): Promise<unknown> {
    try {
      return await this.callTool("get_context_summary", { repo_id: "demo" });
    } catch {
      return null;
    }
  }

  async getRiskScore(modifiedFiles: string[]): Promise<unknown> {
    return this.callTool("get_risk_score", {
      repo_path: this.config.repoPath,
      modified_files: modifiedFiles,
    });
  }

  async searchNodes(query: string, kind?: string): Promise<unknown> {
    return this.callTool("search_nodes", { query, ...(kind ? { kind } : {}) });
  }

  async sreChatQuery(message: string): Promise<unknown> {
    return this.callTool("sre_chat_query", { message });
  }

  async mapMetricToCode(service: string, operation: string): Promise<unknown> {
    return this.callTool("map_metric_to_code", { service, operation });
  }

  async getNode(nodeId: string): Promise<unknown> {
    return this.callTool("get_node", { node_id: nodeId });
  }

  async getEdges(nodeId: string, direction?: string, edgeType?: string): Promise<unknown> {
    return this.callTool("get_edges", {
      node_id: nodeId,
      ...(direction ? { direction } : {}),
      ...(edgeType ? { type: edgeType } : {}),
    });
  }
}