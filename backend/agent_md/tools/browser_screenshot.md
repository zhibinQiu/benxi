---
name: browser_screenshot
---
截取当前浏览器页面图像，用于核对页面视觉状态或留档。

## When to use
- 需要确认页面渲染效果、验证码区域、图表等视觉信息
- 操作后留存截图证据

## When NOT to use
- 需要获取可交互元素 ref（用 browser_snapshot）
- 只需提取公开页正文（用 fetch_url_content）

## Returns
- 截图结果（可含图片资源引用）

## Parameters

### full_page (optional)
是否整页滚动截图。默认 false（当前视口）。
