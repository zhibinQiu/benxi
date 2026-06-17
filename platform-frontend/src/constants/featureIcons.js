import {
  LanguageOutline,
  ChatbubblesOutline,
  MicOutline,
  ScanOutline,
  GitCompareOutline,
  StatsChartOutline,
  SparklesOutline,
  GridOutline,
  DocumentTextOutline,
  ListOutline,
  CreateOutline,
  GitNetworkOutline,
  WalletOutline,
  NewspaperOutline,
  SearchOutline,
  VolumeHighOutline,
} from "@vicons/ionicons5";

/** 与系统功能插件 icon 字段一致 */
export const FEATURE_ICON_MAP = {
  language: LanguageOutline,
  chatbubbles: ChatbubblesOutline,
  mic: MicOutline,
  "volume-high": VolumeHighOutline,
  scan: ScanOutline,
  "git-compare": GitCompareOutline,
  "stats-chart": StatsChartOutline,
  sparkles: SparklesOutline,
  grid: GridOutline,
  "document-text": DocumentTextOutline,
  list: ListOutline,
  create: CreateOutline,
  "git-network": GitNetworkOutline,
  wallet: WalletOutline,
  newspaper: NewspaperOutline,
  search: SearchOutline,
};

export function resolveFeatureIcon(key) {
  if (!key) return null;
  return FEATURE_ICON_MAP[key] || null;
}
