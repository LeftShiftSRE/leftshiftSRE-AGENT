import * as vscode from "vscode";
import { RiskProvider } from "./riskProvider";
import { ImpactProvider } from "./impactProvider";
import { ChatProvider } from "./chatProvider";
import { McpClientManager } from "./mcpClient";
import { getConfig } from "./config";

let mcpClient: McpClientManager | undefined;
let riskProvider: RiskProvider | undefined;
let impactProvider: ImpactProvider | undefined;
let chatProvider: ChatProvider | undefined;
let statusBarItem: vscode.StatusBarItem | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const config = getConfig();

  mcpClient = new McpClientManager(config);
  riskProvider = new RiskProvider(mcpClient);
  impactProvider = new ImpactProvider(mcpClient);
  chatProvider = new ChatProvider(mcpClient, context);

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = "Relic: Initializing...";
  statusBarItem.tooltip = "Relic SRE Agent";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  const parseCmd = vscode.commands.registerCommand("relic.parseRepo", async () => {
    const repoPath = config.repoPath;
    vscode.window.showInformationMessage(`Parsing repository: ${repoPath}`);
    await mcpClient!.ensureParsed(repoPath);
    vscode.window.showInformationMessage("Repository parsed successfully");
  });

  const riskCmd = vscode.commands.registerCommand("relic.riskScore", async () => {
    if (!vscode.workspace.workspaceFolders) {
      vscode.window.showWarningMessage("No workspace folder open");
      return;
    }
    await riskProvider!.updateRiskScore();
  });

  const chatCmd = vscode.commands.registerCommand("relic.openChat", async () => {
    await chatProvider!.show();
  });

  const impactCmd = vscode.commands.registerCommand("relic.impactMap", async () => {
    await impactProvider!.show();
  });

  context.subscriptions.push(parseCmd, riskCmd, chatCmd, impactCmd);

  vscode.window.registerTreeDataProvider("relic.impact", impactProvider);

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (e) => {
      if (config.autoRiskOnSave && e.uri.fsPath.endsWith(".py")) {
        await riskProvider!.updateRiskScore();
      }
    })
  );

  await mcpClient.start();

  const summary = await mcpClient.getContextSummary() as { files?: number } | null;
  if (summary) {
    statusBarItem.text = `Relic: ${summary.files || 0} files indexed`;
  } else {
    statusBarItem.text = "Relic: No .ctx found";
  }
}

export function deactivate() {
  mcpClient?.stop();
}