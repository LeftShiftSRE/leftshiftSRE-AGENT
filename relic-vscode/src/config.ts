import * as vscode from "vscode";

export interface RelicConfig {
  repoPath: string;
  ctxFilePath: string;
  enginePath: string;
  useMockData: boolean;
  splunkMcpUrl: string;
  splunkToken: string;
  autoRiskOnSave: boolean;
}

export function getConfig(): RelicConfig {
  const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ".";
  const cfg = vscode.workspace.getConfiguration("relic");

  return {
    repoPath: cfg.get<string>("repoPath", wsFolder),
    ctxFilePath: cfg.get<string>("ctxFilePath", `${wsFolder}/.ctx/repo.ctx`),
    enginePath: cfg.get<string>("enginePath", "relic"),
    useMockData: cfg.get<boolean>("useMockData", true),
    splunkMcpUrl: cfg.get<string>("splunkMcpUrl", "http://localhost:8089"),
    splunkToken: cfg.get<string>("splunkToken", ""),
    autoRiskOnSave: cfg.get<boolean>("autoRiskOnSave", true),
  };
}