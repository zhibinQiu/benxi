let echartsLoader = null;

/** ECharts 动态加载单例（对话富媒体、图表预览等共用） */
export function loadEcharts() {
  if (!echartsLoader) {
    echartsLoader = import("echarts").then((mod) => mod.default ?? mod);
  }
  return echartsLoader;
}
