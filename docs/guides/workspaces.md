# Workspaces

Citeframe is a self-hosted knowledge workspace for technical research across source documents, images, and media. It is in **Preview**. Model-quality evaluation and validation with target users are pending; format support and viewer depth vary by format.

## Build a knowledge workspace

Create a workspace for a research question or project. Upload supported files from the asset sidebar and wait for processing to finish. A submitted upload still needs parsing and indexing before it is ready for retrieval.

Workspaces separate assets, retrieval scope, conversations, notes, tags, and model settings. Use the question's asset scope to search selected sources or the workspace's ready assets. Model requests require configured generation and embedding capabilities. See [model configuration](model-configuration.md) and [format support](format-support.md).

## Quick Answer and Research

Quick Answer is the default path for focused questions. Responses stream with source citations. Open a citation to inspect the original page, image region, text block, cell range, or media time range.

Research is a bounded workflow for multi-part questions and comparisons. It preserves a plan, execution state, evidence, claim checks, and report artifacts. Workflow versions determine which plan or conflict decisions require confirmation. Historical runs retain their original workflow and model bindings. See [Research execution](../architecture/research-workflow-runtime.md).

Check the cited evidence before relying on a conclusion. Generation can produce unsupported answers, and OCR, parsing, transcription, or retrieval can miss relevant source content. Conflicts or insufficient evidence may remain visible in a report.

## Preserve knowledge

Save a citation as a source-linked note, or create a free note. Tags organize assets and notes within a workspace. Citation and note-source snapshots preserve their original locator and excerpt when an asset is reindexed. After source deletion, the historical snapshot remains readable and the viewer reports that the source is unavailable.

Research report edits are separate editions. Editing does not reverify the text or alter the original report, evidence, or claim journal.

## Current scope

The product focuses on AI/software engineers and technical researchers comparing papers, specifications, evaluations, and design documents. Cross-workspace federated retrieval, a general-purpose plugin or workflow marketplace, and unrestricted agent delegation are outside the current scope.
