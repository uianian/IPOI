/**
 * SettingsDialog — Agent 可选 LLM API 配置
 */
import { useState, useEffect } from "react";
import { Settings } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  getAgentLlmSettings,
  saveAgentLlmSettings,
} from "@/data/settings";
import type { AgentLlmSettings } from "@/types";
import { toast } from "sonner";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function SettingsDialog({
  open,
  onOpenChange,
}: SettingsDialogProps) {
  const [form, setForm] = useState<AgentLlmSettings>({});

  useEffect(() => {
    if (open) setForm(getAgentLlmSettings());
  }, [open]);

  const handleSave = () => {
    saveAgentLlmSettings({
      apiBaseUrl: form.apiBaseUrl?.trim() || undefined,
      apiKey: form.apiKey?.trim() || undefined,
      model: form.model?.trim() || undefined,
    });
    toast.success("设置已保存（仅本机）");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Agent 大模型配置
          </DialogTitle>
          <DialogDescription className="text-xs">
            可选配置。留空则使用后端默认模型。配置仅保存在本机浏览器，不会上传至服务器。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label className="text-xs">API Base URL</Label>
            <Input
              value={form.apiBaseUrl ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, apiBaseUrl: e.target.value }))
              }
              placeholder="https://api.deepseek.com/v1"
              className="h-9 text-sm font-['JetBrains_Mono',monospace]"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">API Key</Label>
            <Input
              type="password"
              value={form.apiKey ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, apiKey: e.target.value }))
              }
              placeholder="sk-..."
              className="h-9 text-sm font-['JetBrains_Mono',monospace]"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Model</Label>
            <Input
              value={form.model ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, model: e.target.value }))
              }
              placeholder="deepseek-chat"
              className="h-9 text-sm font-['JetBrains_Mono',monospace]"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="h-8 text-xs"
          >
            取消
          </Button>
          <Button size="sm" onClick={handleSave} className="h-8 text-xs">
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
