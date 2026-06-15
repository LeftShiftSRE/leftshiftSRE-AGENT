import * as vscode from "vscode";
import { McpClientManager } from "./mcpClient";

interface RiskNodeScore {
  node_id: string;
  node_name: string;
  score: number;
  level: string;
  reasons: string[];
  incidents: { id: string; severity: string; summary: string }[];
  downstream_dependents: { node_id: string; name: string; path: string }[];
  upstream_callers: { node_id: string; name: string; path: string }[];
}

interface RiskResult {
  overall_score: number;
  level: string;
  node_scores: RiskNodeScore[];
}

export class RiskProvider {
  private client: McpClientManager;
  private statusBar: vscode.StatusBarItem;
  private decorations = new Map<string, vscode.TextEditorDecorationType>();
  private currentRisk: RiskResult | null = null;

  constructor(client: McpClientManager) {
    this.client = client;
    this.statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
    this.statusBar.command = "relic.impactMap";
    this.statusBar.show();
  }

  async updateRiskScore(modifiedFiles?: string[]): Promise<void> {
    if (!vscode.workspace.workspaceFolders) return;

    const files = modifiedFiles || this.getModifiedPythonFiles();

    if (files.length === 0) {
      this.statusBar.text = "Relic: 0/100 (low)";
      this.statusBar.color = "#3fb950";
      this.currentRisk = null;
      return;
    }

    try {
      const result = (await this.client.getRiskScore(files)) as RiskResult;
      this.currentRisk = result;
      this.updateStatusBar(result);
      await this.applyDecorations(result);
    } catch (err) {
      this.statusBar.text = "Relic: Error";
      this.statusBar.color = "#f85149";
    }
  }

  private getModifiedPythonFiles(): string[] {
    if (!vscode.workspace.workspaceFolders) return [];

    const repoPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
    const files: string[] = [];

    for (const editor of vscode.window.visibleTextEditors) {
      const doc = editor.document;
      if (doc.uri.fsPath.endsWith(".py") && doc.uri.fsPath.includes(repoPath)) {
        const relPath = doc.uri.fsPath.replace(repoPath + "\\", "").replace(repoPath + "/", "");
        files.push(relPath);
      }
    }

    return files;
  }

  private updateStatusBar(result: RiskResult): void {
    const score = result.overall_score;
    const level = result.level;

    const prefixes: Record<string, string> = {
      low: "[OK]",
      medium: "[WARN]",
      critical: "[CRIT]",
      none: "[---]",
    };

    const colors: Record<string, string> = {
      low: "#3fb950",
      medium: "#d29922",
      critical: "#f85149",
      none: "#3fb950",
    };

    this.statusBar.text = `${prefixes[level] || "[?]"} Relic: ${score}/100`;
    this.statusBar.color = colors[level] || "#cccccc";
    this.statusBar.tooltip = `${level.toUpperCase()} risk\n\nTop reason: ${result.node_scores[0]?.reasons[0] || "none"}\n\nClick to view impact map`;
  }

  private async applyDecorations(result: RiskResult): Promise<void> {
    for (const decoration of this.decorations.values()) {
      decoration.dispose();
    }
    this.decorations.clear();

    for (const editor of vscode.window.visibleTextEditors) {
      for (const nodeScore of result.node_scores) {
        const doc = editor.document;
        if (!doc.uri.fsPath.endsWith(".py")) continue;

        const docPath = doc.uri.fsPath.replace(/\\/g, "/");

        try {
          const nodeInfo = (await this.client.getNode(nodeScore.node_id)) as {
            path: string;
            start_line: number;
            end_line: number;
          } | null;

          if (!nodeInfo || !nodeInfo.path) continue;
          if (!docPath.endsWith(nodeInfo.path)) continue;

          const startLine = Math.max(0, (nodeInfo.start_line || 1) - 1);

          if (nodeScore.level === "critical" || nodeScore.level === "medium") {
            const bgColor = nodeScore.level === "critical"
              ? "rgba(248, 81, 73, 0.1)"
              : "rgba(210, 153, 34, 0.1)";
            const textColor = nodeScore.level === "critical" ? "#f85149" : "#d29922";

            const decoration = vscode.window.createTextEditorDecorationType({
              isWholeLine: true,
              overviewRulerColor: textColor,
              overviewRulerLane: vscode.OverviewRulerLane.Right,
              backgroundColor: bgColor,
              after: {
                contentText: " Risk " + nodeScore.score + "/100",
                color: textColor,
                fontWeight: "bold",
              },
            });

            editor.setDecorations(decoration, [
              new vscode.Range(startLine, 0, startLine, 0),
            ]);

            this.decorations.set(editor.document.uri.fsPath + "-" + nodeScore.node_id, decoration);
          }
        } catch {
          // Node not found in current document
        }
      }
    }
  }

  getCurrentRisk(): RiskResult | null {
    return this.currentRisk;
  }
}