import * as vscode from "vscode";
import { McpClientManager } from "./mcpClient";

interface ImpactNode {
  nodeId: string;
  name: string;
  path: string;
  score?: number;
  level?: string;
  reasons?: string[];
  incidents?: { id: string; severity: string; summary: string }[];
  dependents?: { node_id: string; name: string; path: string }[];
  callers?: { node_id: string; name: string; path: string }[];
}

export class ImpactProvider implements vscode.TreeDataProvider<TreeItem> {
  private client: McpClientManager;
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
  private impactData: ImpactNode[] = [];

  constructor(client: McpClientManager) {
    this.client = client;
  }

  async show(): Promise<void> {
    await this.refresh();
    await vscode.commands.executeCommand("relic.impact.focus");
  }

  async refresh(): Promise<void> {
    try {
      const result = (await this.client.getRiskScore([])) as {
        node_scores: ImpactNode[];
      } | null;

      if (result?.node_scores) {
        this.impactData = result.node_scores;
      } else {
        this.impactData = [];
      }
    } catch {
      this.impactData = [];
    }

    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: TreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: TreeItem): Promise<TreeItem[]> {
    if (!element) {
      if (this.impactData.length === 0) {
        return [new TreeItem("No risk data — save a Python file to see impact", vscode.TreeItemCollapsibleState.None)];
      }

      return this.impactData.map((node) => {
        const icon = this.getSeverityIcon(node.level || "low");
        const label = icon + " " + node.name + "() -- Risk " + (node.score || 0) + "/100";
        const item = new TreeItem(label, vscode.TreeItemCollapsibleState.Expanded);
        item.contextValue = "impactNode";
        item.resourceUri = vscode.Uri.file(node.path);
        item.customId = node.nodeId;
        return item;
      });
    }

    if (element.customId) {
      const node = this.impactData.find((n) => n.nodeId === element.customId);
      if (!node) return [];

      const children: TreeItem[] = [];

      if (node.callers?.length) {
        children.push(new TreeItem("Upstream Callers", vscode.TreeItemCollapsibleState.Collapsed));
      }
      if (node.dependents?.length) {
        children.push(new TreeItem("Downstream Dependents", vscode.TreeItemCollapsibleState.Collapsed));
      }
      if (node.incidents?.length) {
        children.push(new TreeItem("Past Incidents (" + node.incidents.length + ")", vscode.TreeItemCollapsibleState.Collapsed));
      }
      if (node.reasons?.length) {
        children.push(new TreeItem("Reasons", vscode.TreeItemCollapsibleState.Collapsed));
      }

      return children;
    }

    const label = String(element.label || "");
    const parentId = this.findParentId(label);
    if (!parentId) return [];

    const parentNode = this.impactData.find((n) => n.nodeId === parentId);
    if (!parentNode) return [];

    if (label.startsWith("Upstream")) {
      return (parentNode.callers || []).map((c) => {
        const item = new TreeItem(c.name + "()  [" + c.path + "]", vscode.TreeItemCollapsibleState.None);
        item.contextValue = "codeNode";
        item.resourceUri = vscode.Uri.file(c.path);
        item.command = { command: "vscode.open", arguments: [vscode.Uri.file(c.path)], title: "Open file" };
        return item;
      });
    }

    if (label.startsWith("Downstream")) {
      return (parentNode.dependents || []).map((d) => {
        const item = new TreeItem(d.name + "()  [" + d.path + "]", vscode.TreeItemCollapsibleState.None);
        item.contextValue = "codeNode";
        item.resourceUri = vscode.Uri.file(d.path);
        item.command = { command: "vscode.open", arguments: [vscode.Uri.file(d.path)], title: "Open file" };
        return item;
      });
    }

    if (label.startsWith("Past Incidents")) {
      return (parentNode.incidents || []).map((inc) => {
        const sev = inc.severity === "critical" ? "[CRIT]" : inc.severity === "high" ? "[HIGH]" : "[MED]";
        const item = new TreeItem(sev + " " + inc.id + ": " + inc.summary.substring(0, 60), vscode.TreeItemCollapsibleState.None);
        item.contextValue = "incident";
        return item;
      });
    }

    if (label.startsWith("Reasons")) {
      return (parentNode.reasons || []).map((reason: string) => {
        return new TreeItem(reason, vscode.TreeItemCollapsibleState.None);
      });
    }

    return [];
  }

  private findParentId(label: string): string | undefined {
    for (const node of this.impactData) {
      if (label.includes(node.name)) {
        return node.nodeId;
      }
    }
    return undefined;
  }

  private getSeverityIcon(level: string): string {
    switch (level) {
      case "critical": return "[CRIT]";
      case "medium": return "[MED]";
      case "low": return "[LOW]";
      default: return "[---]";
    }
  }
}

class TreeItem extends vscode.TreeItem {
  public customId?: string;

  constructor(label: string, collapsibleState: vscode.TreeItemCollapsibleState) {
    super(label, collapsibleState);
  }
}