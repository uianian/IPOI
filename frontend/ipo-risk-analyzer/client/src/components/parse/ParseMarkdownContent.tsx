/**
 * ParseMarkdownContent — 解析结果 Markdown + HTML 混排渲染
 */
import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

interface ParseMarkdownContentProps {
  content: string;
  className?: string;
}

export default function ParseMarkdownContent({
  content,
  className,
}: ParseMarkdownContentProps) {
  return (
    <div className={cn("parse-markdown overflow-x-auto", className)}>
      <Streamdown
        isAnimating={false}
        className="prose prose-sm prose-invert max-w-none font-['IBM_Plex_Sans',sans-serif] text-foreground leading-relaxed text-sm"
      >
        {content}
      </Streamdown>
    </div>
  );
}
