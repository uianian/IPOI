import {
  Building2,
  Languages,
  Landmark,
  Calendar,
  Tag,
  MapPin,
  SearchX,
} from "lucide-react";
import type { CompanyRecord } from "@/types";

interface BasicInfoCardProps {
  /** 按 Wind 代码 join 到的真实公司记录，未查到为 null */
  record: CompanyRecord | null;
  /** 用于未查到时提示的股票代码 */
  ticker?: string;
}

export default function BasicInfoCard({ record, ticker }: BasicInfoCardProps) {
  const items = record
    ? [
        { icon: Building2, label: "公司中文名称", value: record.companyName },
        { icon: Languages, label: "公司英文名称", value: record.nameEng },
        { icon: Tag, label: "证券简称", value: record.name },
        { icon: Calendar, label: "上市日期", value: record.listDate },
        { icon: Landmark, label: "上市板", value: record.listBoard },
        { icon: MapPin, label: "注册地所在国家或地区", value: record.country },
      ]
    : [];

  return (
    <div className="panel-glass rounded-xl p-5 space-y-4">
      <div className="text-[10px] text-muted-foreground font-['JetBrains_Mono',monospace] tracking-widest">
        COMPANY INFO
      </div>

      {record ? (
        <div className="grid grid-cols-2 gap-2">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="flex items-start gap-2 p-2 rounded-lg bg-[oklch(0.75_0.18_195)/0.06] border border-[oklch(0.75_0.18_195)/0.15]"
              >
                <Icon className="w-3 h-3 text-primary flex-shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-[10px] text-muted-foreground">
                    {item.label}
                  </p>
                  <p className="text-xs font-medium text-foreground break-words">
                    {item.value || "—"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <SearchX className="w-6 h-6 text-muted-foreground/50 mb-2" />
          <p className="text-xs text-muted-foreground">
            未查询到{ticker ? ` ${ticker} ` : ""}的公司信息
          </p>
          <p className="text-[10px] text-muted-foreground/70 mt-1">
            请确认 Wind 代码或股票代码是否正确
          </p>
        </div>
      )}
    </div>
  );
}
