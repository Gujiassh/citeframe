# PDF 页内视觉 v1

Date: 2026-08-13  
Status: **in progress**（2026-08-13：worker 已实现无 XObject 图块检测 + 区域 OCR + 抽象图 fail-closed caption；Chat 带裁切图未改 save contract）  
Parent: [`current-execution-plan.md`](current-execution-plan.md)

## 1. 问题

没有 **内嵌 Image XObject** 的 PDF，页上的截图 / 贴图 / 抽象图当前无法稳定识别：

- 抽图依赖 `get_image_info()`  
- 整页 OCR 主要在「几乎无文本层」时触发  
- 有文本 + 压平图 → 图漏检  

## 2. 目标

| 输入 | 期望 |
|---|---|
| 无内嵌图 + 带字截图 | 检出 region；OCR 文本可检索；可高亮 |
| 无内嵌图 + 抽象图（流程/架构） | 检出 region；caption（gpt-5.5）；问答可带裁切图引用 |
| 有内嵌图 | 保持/加固现有 figure 路径 + 区域 OCR/caption |

仍挂在 **同一 PDF Asset** 上，不拆成独立 Image Asset。

## 3. 管道

```text
Page
  → candidates =
        embedded images (existing)
      ∪ rendered visual blocks (new; no embed required)
  → per candidate:
        crop → OCR text?
        crop → caption via vision capability (gpt-5.5)
  → ContentUnits + pdf_region / pdf_figure locators
  → retrieval
  → Chat/Research: on hit, attach crop image to generation
```

## 4. 模型

| 步骤 | 模型/引擎 |
|---|---|
| OCR | 现有 RapidOCR 路径 |
| Caption | 现有 `image_caption` / **gpt-5.5**（CLIProxy preview）；**抽象图必选，不可仅 OCR** |
| 问答带图 | 现有 generation / **gpt-5.5** |

同一 OpenAI 兼容 profile；换模要升 version/fingerprint 并显式 reprocess。

## 5. 非目标（v1）

- 精确数步骤/读表结构到单元格级（可后置）  
- 把每个 figure 升成独立 Image 资产  
- 未检出 region 就整页丢给 VL 瞎看  

## 6. 验收

1. Fixture：无内嵌图 + 截图有字 → 检索命中截图文字 + region 高亮  
2. Fixture：无内嵌图 + 流程图 → 有 region + 非空 caption；问答引用该 region  
3. 有内嵌图回归不回退  
4. 无 vision key 时 caption fail-closed，不写假描述  

## 7. 与 V5-F 其它模态

HTML/Video 复用同一 **VisualRegion 概念**（OCR+caption+带图问答），但区域来源各自定义；本文件只冻结 **PDF**。
