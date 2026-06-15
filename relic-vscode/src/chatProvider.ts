import * as vscode from "vscode";
import * as path from "path";
import { McpClientManager } from "./mcpClient";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface SREChatResult {
  intent: string;
  spl_query: string;
  results: Record<string, unknown>[];
  code_mappings: { node_id: string; file: string; line: number; function: string }[];
  suggestions: string[];
}

export class ChatProvider {
  private client: McpClientManager;
  private context: vscode.ExtensionContext;
  private panel: vscode.WebviewPanel | null = null;
  private messages: ChatMessage[] = [];
  private isProcessing = false;

  constructor(client: McpClientManager, context: vscode.ExtensionContext) {
    this.client = client;
    this.context = context;
  }

  async show(): Promise<void> {
    if (this.panel) {
      this.panel.reveal(vscode.ViewColumn.Bottom, true);
      return;
    }

    this.panel = vscode.window.createWebviewPanel(
      "relicSreChat",
      "Relic SRE Chat",
      { viewColumn: vscode.ViewColumn.Bottom, preserveFocus: true },
      { retainContextWhenHidden: true, enableScripts: true }
    );

    this.panel.webview.html = this.getWebviewContent();
    this.panel.webview.onDidReceiveMessage((msg) => this.handleMessage(msg));
    this.panel.onDidDispose(() => {
      this.panel = null;
    });
  }

  private async handleMessage(msg: { type: string; text?: string }): Promise<void> {
    if (msg.type === "send" && msg.text && !this.isProcessing) {
      const userMessage = msg.text.trim();
      if (!userMessage) return;

      this.isProcessing = true;
      this.addMessage("user", userMessage);
      this.addMessage("assistant", "Thinking...");
      this.render();

      try {
        const result = (await this.client.sreChatQuery(userMessage)) as SREChatResult;
        this.messages.pop();

        const splBlock = `\`\`\`spl\n${result.spl_query}\n\`\`\``;
        const resultsCount = result.results?.length || 0;
        const resultsText = result.results
          ?.slice(0, 5)
          .map((r: Record<string, unknown>) => `| ${r["operation"] || r["service"] || "—"} | ${r["message"] || r["count"] || r["p99_latency_ms"] || "—"} |`)
          .join("\n");

        let response = `**Intent:** ${result.intent}\n\n**Generated SPL:**\n${splBlock}\n\n`;
        if (resultsCount > 0) {
          response += `**Results (${resultsCount}):**\n| Operation | Value |\n|---|---|\n${resultsText}\n\n`;
        }
        if (result.code_mappings?.length) {
          response += `**Code mappings:**\n`;
          for (const cm of result.code_mappings) {
            response += `- \`${cm.function}()\` → ${cm.file}:${cm.line}\n`;
          }
          response += "\n";
        }
        if (result.suggestions?.length) {
          response += `**Suggestions:**\n`;
          for (const s of result.suggestions) {
            response += `- ${s}\n`;
          }
        }

        this.addMessage("assistant", response);
      } catch (err) {
        this.messages.pop();
        this.addMessage("assistant", `Sorry, I encountered an error: ${err}`);
      }

      this.isProcessing = false;
      this.render();
    } else if (msg.type === "suggestion") {
      const userMessage = msg.text || "";
      this.messages.push({ role: "user", content: userMessage });
      this.messages.push({ role: "assistant", content: "Thinking..." });
      this.render();

      try {
        const result = (await this.client.sreChatQuery(userMessage)) as SREChatResult;
        this.messages.pop();
        const splBlock = `\`\`\`spl\n${result.spl_query}\n\`\`\``;
        this.addMessage("assistant", `**SPL:**\n${splBlock}\n\nFound ${result.results?.length || 0} results.`);
      } catch {
        this.messages.pop();
        this.addMessage("assistant", "Could not process suggestion.");
      }

      this.isProcessing = false;
      this.render();
    }
  }

  private addMessage(role: "user" | "assistant", content: string): void {
    this.messages.push({ role, content });
  }

  private render(): void {
    if (!this.panel) return;

    const html = this.getWebviewContent();
    this.panel.webview.postMessage({ type: "render", messages: this.messages });
  }

  private getWebviewContent(): string {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--vscode-font-family); font-size: 13px; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); height: 100vh; display: flex; flex-direction: column; }
    .header { padding: 10px 16px; background: var(--vscode-titleBar-activeBackground); border-bottom: 1px solid var(--vscode-panel-border); display: flex; align-items: center; gap: 8px; }
    .header .icon { font-size: 16px; }
    .header h3 { font-size: 13px; font-weight: 600; }
    .messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 100%; }
    .msg.user { align-self: flex-end; background: var(--vscode-button-background, #0066cc); color: white; padding: 8px 12px; border-radius: 12px 12px 0 12px; max-width: 70%; }
    .msg.assistant { align-self: flex-start; background: var(--vscode-textCodeBlock-background, #2d2d2d); padding: 8px 12px; border-radius: 0 12px 12px 12px; max-width: 100%; white-space: pre-wrap; font-family: var(--vscode-editor-font-family); font-size: 12px; }
    .msg.assistant code { background: #1a1a1a; padding: 2px 5px; border-radius: 3px; font-size: 11px; }
    .msg pre { background: #1a1a1a; padding: 8px; border-radius: 4px; overflow-x: auto; margin: 4px 0; }
    .msg pre code { background: none; padding: 0; }
    .input-area { padding: 10px 16px; border-top: 1px solid var(--vscode-panel-border); display: flex; gap: 8px; background: var(--vscode-input-background); }
    #chatInput { flex: 1; background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border); color: var(--vscode-input-foreground); padding: 6px 10px; border-radius: 4px; font-size: 13px; font-family: var(--vscode-font-family); outline: none; }
    #chatInput:focus { border-color: var(--vscode-focusBorder, #0066cc); }
    #sendBtn { background: var(--vscode-button-background, #0066cc); color: var(--vscode-button-foreground, white); border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; }
    #sendBtn:hover { background: var(--vscode-button-hoverBackground); }
    #sendBtn:disabled { opacity: 0.5; cursor: not-allowed; }
    .suggestion { font-size: 11px; color: var(--vscode-textLink-foreground, #3794ff); cursor: pointer; margin-top: 4px; display: inline-block; }
  </style>
</head>
<body>
  <div class="header">
    <span class="icon">$(bot)</span>
    <h3>Relic SRE Chat</h3>
  </div>
  <div class="messages" id="messages"></div>
  <div class="input-area">
    <input type="text" id="chatInput" placeholder="Ask about errors, latency, incidents... e.g. 'What errors has payment_service had?'" />
    <button id="sendBtn">Send</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const messagesEl = document.getElementById("messages");
    const chatInput = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");

    function renderMessages(messages) {
      messagesEl.innerHTML = messages.map(m =>
        \`<div class="msg \${m.role}">\${m.content}</div>\`
      ).join("");
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function send() {
      const text = chatInput.value.trim();
      if (!text) return;
      chatInput.value = "";
      vscode.postMessage({ type: "send", text });
    }

    sendBtn.addEventListener("click", send);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });

    window.addEventListener("message", (event) => {
      if (event.data.type === "render") {
        renderMessages(event.data.messages);
      }
    });

    chatInput.focus();
  </script>
</body>
</html>`;
  }
}