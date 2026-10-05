# simulation-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/simulation-agent)

`sim` is the VibeBB plugin that checks your hardware design **before you
build it**. It answers one question honestly: is the circuit, the power, the
heat, the strength, the radio behavior, and the testability of this design
OK — and it only says "pass" when the numbers prove it.

## What it does for you

You describe the design and your limits — component values, voltages,
temperatures, loads, board rules — in a small JSON file (the *brief*), or a
sister plugin hands it over. `sim` then runs deterministic checks and real
solver programs and answers with **pass**, **fail**, or **unknown**.
`unknown` is honest: it means information or a tool is missing, never that
things are fine.

## What you give

- Your requirements and limits (numbers, bounds, acceptance criteria).
- Files from sister plugins — circuit, mechanical, wire, or UX data
  imported as hash-verified contracts.
- Optionally, your own SPICE netlists, Touchstone files, or test-point
  layouts.

## What you get back

- A `sim-report` (JSON + readable Markdown) with per-check verdicts and
  the numbers behind them.
- PNG plots for every analysis — summary, margins, waveforms, board
  test-point maps, deflection curves — that you and the agent can look at.
- Records explaining *why*: decisions with reasons, what was seen in each
  image, and long-form impressions, kept as an auditable trail.

## How it works with sister plugins

`sim` is the analysis sister of the VibeBB family: circuit, mech, wire,
bard, firmware, fpga, prodeng, dashboard, doc, and **ux-creator**, which
directs multi-agent work through liaison requests under `liaison/`. Every
exchange is a validated JSON file in the shared workspace — nothing is
imported across repos.

## Getting started

1. Install the `sim` plugin in OpenHands (or AgentCanvas) and make Docker
   available — plugin tools run inside the pinned `sim-tools` image.
2. Run `/sim:doctor` to check solver availability.
3. Give the agent your design or run `/sim:run <brief>` yourself.
4. Talk to the agent: it writes the brief, runs the analyses, looks at the
   plots, and records why it concluded what it concluded.

## Limits

- Models are simplified first-order checks plus solver runs — they are not
  a certification and do not replace measurement of real hardware.
- `unknown` means missing evidence, not "probably fine".
- The optional openEMS image (`sim-tools-em`) is not published yet.

## Safety

- Docker-only, no network access needed for analysis.
- All paths stay inside the workspace; symlink escapes are rejected.
- Generated files (reports, plots, responses, records) are protected and
  regenerated from inputs, never hand-edited.
- Only deterministic gates can emit `pass` — no AI judgment can promote a
  result.

Developer and CI documentation lives in [docs/](docs/README.md).

## 日本語

`sim` は、ハードウェア設計を**作る前に**チェックする VibeBB プラグインです。
回路・電源・熱・強度・無線特性・テスト性が大丈夫かどうかを正直に答えます。
「pass」と言うのは、数字が証明したときだけです。

### 何をしてくれるか

設計と制約条件 — 部品の値、電圧、温度、負荷、基板ルール — を小さな JSON
ファイル(*ブリーフ*)に書くか、姉妹(sister)プラグインが渡します。`sim` は
決定論的チェックと実際のソルバーを実行し、**pass** / **fail** /
**unknown** で答えます。`unknown` は正直な答えです:情報やツールが
足りないという意味であって、問題ないという意味ではありません。

### 何を用意するか

- 要件と限界値(数値、範囲、合否基準)。
- 姉妹プラグインからのファイル — 回路・機械・ワイヤー・UX のデータを
  ハッシュ検証済みの契約としてインポート。
- 必要に応じて、SPICE ネットリスト、Touchstone ファイル、
  テストポイント配置。

### 何が返ってくるか

- `sim-report`(JSON + 読みやすい Markdown)。チェックごとの判定と
  その根拠となる数値。
- 全解析の PNG プロット — サマリー、マージン、波形、基板テストポイント
  マップ、たわみ曲線。あなたもエージェントも見られます。
- 「なぜそうなったか」の記録:理由付きの決定、各画像で見たこと、
  詳細な所感。監査できる記録として残ります。

### 姉妹プラグインとの連携

`sim` は VibeBB ファミリーの解析担当です:circuit、mech、wire、bard、
firmware、fpga、prodeng、dashboard、doc、そして `liaison/` 経由で
マルチエージェント作業を指揮する **ux-creator**。すべてのやり取りは
共有ワークスペース内の検証済み JSON ファイルです。リポジトリをまたいだ
インポートは一切ありません。

### はじめ方

1. OpenHands(または AgentCanvas)に `sim` プラグインをインストールし、
   Docker を使えるようにします。プラグインツールは固定の
   `sim-tools` イメージ内で動きます。
2. `/sim:doctor` でソルバーの有無を確認します。
3. エージェントに設計を渡すか、自分で `/sim:run <brief>` を実行します。
4. エージェントと会話します:ブリーフを書き、解析を実行し、
   プロットを見て、結論の理由を記録します。

### 限界

- モデルは一次近似チェックとソルバー実行であり、認証ではありません。
  実機の計測の代替にはなりません。
- `unknown` は「多分大丈夫」ではなく、証拠不足を意味します。
- オプションの openEMS イメージ(`sim-tools-em`)は未公開です。

### 安全性

- Docker 専用。解析にネットワークアクセスは不要です。
- すべてのパスはワークスペース内に限定。シンボリックリンクの脱出は
  拒否されます。
- 生成ファイル(レポート、プロット、応答、記録)は保護され、
  入力から再生成されます。手編集はできません。
- `pass` を出せるのは決定論的ゲートだけです。AI の判断で結果を
  引き上げることはできません。

開発者・CI 向けドキュメントは [docs/](docs/README.md) にあります。
