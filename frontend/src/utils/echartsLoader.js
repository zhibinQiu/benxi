/**
 * ECharts 动态加载单例（按需注册，减少打包体积）
 *
 * 只注册项目中实际使用的图表类型与组件，
 * 避免全量引入 echarts（~1.2MB → ~300KB）。
 * 如需新增图表类型，在下方注册即可。
 */

let echartsLoader = null;

/** 项目中使用的图表类型列表（按需添加） */
const USED_CHARTS = () => [
  import("echarts/charts").then((m) => ({
    BarChart: m.BarChart,
    LineChart: m.LineChart,
    PieChart: m.PieChart,
    ScatterChart: m.ScatterChart,
    RadarChart: m.RadarChart,
  })),
];

/** 项目中使用的组件列表 */
const USED_COMPONENTS = () => [
  import("echarts/components").then((m) => ({
    GridComponent: m.GridComponent,
    TooltipComponent: m.TooltipComponent,
    LegendComponent: m.LegendComponent,
    ToolboxComponent: m.ToolboxComponent,
    DataZoomComponent: m.DataZoomComponent,
    VisualMapComponent: m.VisualMapComponent,
    MarkLineComponent: m.MarkLineComponent,
  })),
];

/** 项目中使用的渲染器 */
const USED_RENDERERS = () => [
  import("echarts/renderers").then((m) => ({
    CanvasRenderer: m.CanvasRenderer,
  })),
];

/**
 * ECharts 动态加载单例
 * 按需注册图表类型、组件和渲染器，避免全量打包
 */
export function loadEcharts() {
  if (!echartsLoader) {
    echartsLoader = (async () => {
      const [core, charts, comps, renderers] = await Promise.all([
        import("echarts/core").then((m) => m),
        ...USED_CHARTS(),
        ...USED_COMPONENTS(),
        ...USED_RENDERERS(),
      ]);

      const { use } = core;

      use([
        ...Object.values(charts),
        ...Object.values(comps),
        ...Object.values(renderers),
      ]);

      return core;
    })();
  }
  return echartsLoader;
}

/**
 * 兼容旧代码的全量导入（用于快速切换，不推荐长期使用）
 * 当按需注册缺少某些图表类型时报错时，可临时切回全量
 */
export function loadEchartsFull() {
  if (!echartsLoader) {
    echartsLoader = import("echarts").then((mod) => mod.default ?? mod);
  }
  return echartsLoader;
}
