/**
 * CreateProjectDialog — 首页上传弹窗
 */
import { useState, useCallback } from "react";
import { useLocation } from "wouter";
import { Hash, Info, Upload, FileText } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import FileDropZone from "@/components/file/FileDropZone";
import ParseProgressBar from "@/components/parse/ParseProgressBar";
import BiotechSelector from "@/components/project/BiotechSelector";
import ProfessionalModeSelector from "@/components/project/ProfessionalModeSelector";
import { createProject, updateProject } from "@/data/projects";
import { saveSourcePdf } from "@/data/projectStore";
import { useActiveProject } from "@/contexts/ActiveProjectContext";
import {
  resolveTickerForBackend,
  isValidTickerInput,
} from "@/lib/companyLookup";
import { toast } from "sonner";

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onProjectCreated?: () => void;
}

export default function CreateProjectDialog({
  open,
  onOpenChange,
  onProjectCreated,
}: CreateProjectDialogProps) {
  const [, navigate] = useLocation();
  const { setActiveProjectId } = useActiveProject();
  const [file, setFile] = useState<File | null>(null);
  const [ticker, setTicker] = useState("");
  const [projectName, setProjectName] = useState("");
  const [isBiotech, setIsBiotech] = useState<boolean | null>(null);
  const [enableEmbellishment, setEnableEmbellishment] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("INIT");

  const reset = () => {
    setFile(null);
    setTicker("");
    setProjectName("");
    setIsBiotech(null);
    setEnableEmbellishment(false);
    setIsProcessing(false);
    setProgress(0);
    setStage("INIT");
  };

  const handleUpload = useCallback(async () => {
    if (!file) {
      toast.error("请上传招股书PDF文件");
      return;
    }
    if (!ticker.trim()) {
      toast.error("请输入股票代码");
      return;
    }
    if (!isValidTickerInput(ticker)) {
      toast.error("股票代码格式不正确，请输入 Wind 代码或 1–5 位数字");
      return;
    }
    if (isBiotech === null) {
      toast.error("请选择是否为生物科技公司");
      return;
    }

    setIsProcessing(true);
    setStage("UPLOADING");
    setProgress(0);

    try {
      const resolvedTicker = await resolveTickerForBackend(ticker);
      const project = createProject(
        file.name,
        resolvedTicker,
        isBiotech,
        projectName,
        enableEmbellishment
      );

      // 本地缓存 PDF + 模拟本地写入进度
      let p = 0;
      await new Promise<void>((resolve) => {
        const interval = setInterval(() => {
          p = Math.min(100, p + 20);
          setProgress(p);
          if (p >= 100) {
            clearInterval(interval);
            resolve();
          }
        }, 120);
      });

      await saveSourcePdf(project.id, file);
      updateProject(project.id, { status: "parsing", parseProgress: 0 });
      setStage("READY");
      setActiveProjectId(project.id);

      setTimeout(() => {
        onOpenChange(false);
        onProjectCreated?.();
        reset();
        toast.success("上传完成，开始解析");
        navigate(`/project/${project.id}`);
      }, 400);
    } catch {
      toast.error("创建项目失败");
      setIsProcessing(false);
    }
  }, [
    file,
    ticker,
    projectName,
    isBiotech,
    enableEmbellishment,
    navigate,
    onOpenChange,
    onProjectCreated,
    setActiveProjectId,
  ]);

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (isProcessing) return;
        if (!o) reset();
        onOpenChange(o);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base">创建新项目</DialogTitle>
          <DialogDescription className="text-xs">
            上传港股IPO企业招股书PDF，系统将自动解析并驱动多Agent协同分析
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2 overflow-hidden min-w-0">
          <FileDropZone
            file={file}
            onFileSelect={setFile}
            onFileRemove={() => setFile(null)}
            disabled={isProcessing}
          />

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Hash className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs font-medium text-foreground">
                股票代码
              </span>
            </div>
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="例：0084.HK 或 0084"
              disabled={isProcessing}
              className="bg-secondary border-border text-foreground placeholder:text-muted-foreground font-['JetBrains_Mono',monospace] text-sm h-9"
            />
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
              <p className="text-[10px] text-muted-foreground">
                支持 Wind 代码（如 0084.HK）或股票代码（如 0084）；系统将同步获取公司信息与市场行情数据
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs font-medium text-foreground">
                项目名称
              </span>
              <span className="text-[10px] text-muted-foreground">(可选)</span>
            </div>
            <Input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="例：阿里 IPO 招股书分析"
              disabled={isProcessing}
              className="bg-secondary border-border text-foreground placeholder:text-muted-foreground text-sm h-9"
            />
            <div className="flex items-start gap-1.5">
              <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
              <p className="text-[10px] text-muted-foreground">
                仅用于项目列表识别，不影响解析与后端接口
              </p>
            </div>
          </div>

          <BiotechSelector
            value={isBiotech}
            onChange={setIsBiotech}
            disabled={isProcessing}
          />

          <ProfessionalModeSelector
            value={enableEmbellishment}
            onChange={setEnableEmbellishment}
            disabled={isProcessing}
          />

          {isProcessing && (
            <ParseProgressBar progress={progress} stage={stage} />
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isProcessing}
            className="h-8 text-xs"
          >
            取消
          </Button>
          <Button
            onClick={handleUpload}
            disabled={isProcessing || !file || !ticker.trim() || isBiotech === null}
            size="sm"
            className="h-8 text-xs gap-1.5"
            style={{
              background: "oklch(0.75 0.18 195)",
              color: "oklch(0.10 0.012 240)",
            }}
          >
            <Upload className="w-3.5 h-3.5" />
            {isProcessing ? "上传中..." : "上传"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
