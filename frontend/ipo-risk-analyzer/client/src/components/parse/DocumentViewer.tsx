/**
 * DocumentViewer — 文档预览（Markdown）
 */
import { FileType2 } from "lucide-react";
import { cn } from "@/lib/utils";
import ParseMarkdownContent from "@/components/parse/ParseMarkdownContent";

interface DocumentViewerProps {
  markdown: string | null;
  className?: string;
}

export default function DocumentViewer({
  markdown,
  className,
}: DocumentViewerProps) {
  if (!markdown) {
    return (
      <div className={cn("panel-glass rounded-xl p-8", className)}>
        <div className="flex flex-col items-center justify-center text-center space-y-3">
          <FileType2 className="w-10 h-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            文档预览将在解析完成后显示
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("panel-glass rounded-xl overflow-hidden", className)}>
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-secondary/30">
        <span className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest">
          DOCUMENT PREVIEW
        </span>
      </div>

      <div className="p-5 min-h-[320px] max-h-[600px] overflow-auto">
        <ParseMarkdownContent content={markdown} />
      </div>
    </div>
  );
}
