# simulation-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/simulation-agent)

`sim` is an OpenHands plugin for deterministic, fail-closed engineering
simulation analysis. It complements circuit, mechanical, wire, UX, and bard
agents through versioned JSON files in the shared workspace; it does not import
sibling packages.

## Install

Install the `sim` plugin in OpenHands and make Docker available for the locked
solver image. The launcher defaults to Docker and requires Docker plus a
resolvable tools image; set `SIM_TOOLS_IMAGE` to select one. Set
`SIM_LAUNCH_MODE=host` to run with the host Python environment, or `auto` to
retain Docker-when-available behavior. Run `/sim:doctor` to inspect solver
availability.

## Commands

The plugin provides `/sim:doctor`, `/sim:run`, `/sim:spice`, `/sim:pdn`,
`/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, `/sim:rf`,
`/sim:gates`, `/sim:import`, and `/sim:respond`.

## Hooks

Session start runs `sim-doctor`, `intake-attachments`, and
`ensure-llm-profiles`. Attachment intake also runs on user prompts and
session stop. `inspect_image_with_vision` responses and `file_editor` image
views are recorded by post-tool hooks under `observations/sim/`; these records
are advisory evidence and never affect deterministic verdicts.

The JSON CLI is also available as `python -m sim`:

```bash
python -m sim doctor --warn
python -m sim validate examples/buck-regulator/buck.sim.json
python -m sim gates examples/buck-regulator/buck.sim.json
python -m sim respond examples/buck-regulator/buck.sim-request.json
```

CLI output is JSON. Exit status is 0 for `pass`, 1 for `fail`, 3 for
`unknown`, and 2 for usage or input errors. Generated artifacts are written
under `out/<name>/`: `sim-report.json`, `sim-report.md`, `manifest.json`,
`provenance.json`, and adapter output. These are projections of the brief and
must not be edited by hand.

## Analyses

| Analysis | Method |
| --- | --- |
| SPICE | Unmodified `ngspice` batch process; parse declared `.meas` results |
| PDN | DC nodal solve, copper temperature correction, IPC-2221 trace ampacity |
| Thermal | Scalar resistance paths or thermal nodal networks |
| WCA | Restricted expression AST; EVA, RSS, seeded Monte Carlo, bounded SPICE corners |
| EMC / ESD | Declared-data TVS, placement, critical-length, reference-plane, and decoupling rules |
| DFT | Test-point coverage, pad diameter, pitch, debug-header, and boundary-scan rules |
| FEM | CalculiX subprocess for a cantilever box plus an Euler–Bernoulli estimate |
| RF | Touchstone v1 band checks, optional KiCad-rfsim/openEMS subprocess, microstrip estimate |

Only deterministic analysis code emits verdicts. `fail` blocks acceptance;
`unknown` is unresolved and never becomes `pass` because a tool exited
successfully or an agent inferred a result. Analytic estimates are labelled and
do not replace unavailable solver output.

## Sibling cooperation

Simulation briefs (`*.sim.json`), imports (`*.connectivity.json`,
`*.envelope.json`, `*.contract.json`), and requests/responses (`*.sim-request.json`,
`*.sim-response.json`) are strict, versioned JSON contracts. Each imported file
is validated by local mirror models and recorded with its SHA-256 digest.
Declare consumed imports in the brief; every run rebuilds `imports.json` from
those validated declarations rather than trusting prior generated output.
Unsupported or malformed sibling content remains unknown; no sibling Python
package is imported.

## Development

Python 3.14+, uv `0.12.23`, and Docker are used by the repository workflow.
The `workflow-lint.yml` job runs actionlint 1.7.12 and zizmor 1.30.1 on pull
requests, workflow changes to main, manual dispatch, and weekly.

```bash
uv sync --locked
uv run python scripts/verify_all.py --stage fast
uv run python scripts/check_plugin_load.py
uv run python scripts/verify_all.py --stage standard
actionlint
uvx zizmor@1.30.1 --format plain .github/workflows
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
uv run python scripts/smoke_image.py --image sim-tools:local
```

See [operations](docs/operations.md), [architecture](docs/architecture.md),
and [Docker notes](docker/README.md) for implementation and deployment
boundaries. The [ADRs](docs/adr/) include
[ADR-0006: Docker-only launcher default](docs/adr/0006-docker-only-launcher-default.md)
and
[ADR-0007: Attest published tools images](docs/adr/ADR-0007-attest-published-tools-images.md).

## 日本語

`sim` は決定論的でフェイルクローズなエンジニアリングシミュレーション解析のための
OpenHands プラグインです。共有ワークスペース内のバージョン管理された JSON ファイルを
通じて回路・メカ・ワイヤ・UX・bard の各エージェントを補完し、姉妹パッケージを
インポートしません。

### インストール

OpenHands に `sim` プラグインをインストールし、ロックされたソルバーイメージ用に
Docker を利用可能にしてください。ランチャーは既定で Docker を使い、Docker と
解決可能なツールイメージを必要とします。`SIM_TOOLS_IMAGE` でイメージを選択、
`SIM_LAUNCH_MODE=host` でホスト Python 環境での実行、`auto` で Docker 利用時のみ
Docker の動作を維持できます。`/sim:doctor` でソルバーの有無を確認できます。

### コマンド

`/sim:doctor`、`/sim:run`、`/sim:spice`、`/sim:pdn`、`/sim:thermal`、
`/sim:wca`、`/sim:emc`、`/sim:dft`、`/sim:fem`、`/sim:rf`、`/sim:gates`、
`/sim:import`、`/sim:respond`。

### フック

セッション開始時に `sim-doctor`、`intake-attachments`、`ensure-llm-profiles` を
実行します。添付ファイルの取り込みはユーザープロンプト時とセッション停止時にも
動作します。`inspect_image_with_vision` の応答と `file_editor` の画像表示は
ポストツールフックで `observations/sim/` に記録され、これらは助言的証拠であり
決定論的な判定に影響しません。

JSON CLI は `python -m sim` としても利用できます:

```bash
python -m sim doctor --warn
python -m sim validate examples/buck-regulator/buck.sim.json
python -m sim gates examples/buck-regulator/buck.sim.json
python -m sim respond examples/buck-regulator/buck.sim-request.json
```

CLI の出力は JSON です。終了コードは `pass` が 0、`fail` が 1、`unknown` が 3、
用法・入力エラーが 2。生成物は `out/<name>/` 配下に書き出され、ブリーフの
投影であるため手編集してはいけません。

### 解析

| 解析 | 方式 |
| --- | --- |
| SPICE | 無改造 `ngspice` バッチプロセス。宣言された `.meas` 結果をパース |
| PDN | DC ノード解析、銅温度補正、IPC-2221 トレース許容電流 |
| 熱 | スカラー抵抗経路または熱ノードネットワーク |
| WCA | 制限式 AST。EVA、RSS、シード付きモンテカルロ、境界付き SPICE コーナー |
| EMC / ESD | 宣言データの TVS、配置、臨界長、リファレンス面、デカップリングルール |
| DFT | テストポイントカバレッジ、パッド径、ピッチ、デバッグヘッダ、バウンダリスキャンルール |
| FEM | 片持ち梁ボックスの CalculiX サブプロセス + オイラー・ベルヌーイ推定 |
| RF | Touchstone v1 帯域チェック、任意で KiCad-rfsim/openEMS サブプロセス、マイクロストリップ推定 |

判定を発するのは決定論的な解析コードのみです。`fail` は受理をブロックし、
`unknown` は未解決のまま残り、ツールが正常終了したことやエージェントの推論で
`pass` になることはありません。解析推定はラベル付けされ、利用不可のソルバー
出力の代替にはなりません。

### 姉妹連携

シミュレーションブリーフ（`*.sim.json`）、インポート（`*.connectivity.json`、
`*.envelope.json`、`*.contract.json`）、リクエスト/レスポンス
（`*.sim-request.json`、`*.sim-response.json`）は厳格でバージョン管理された
JSON コントラクトです。各インポートファイルはローカルのミラーモデルで検証され、
SHA-256 ダイジェストとともに記録されます。未対応または不正な姉妹コンテンツは
unknown のままです。姉妹の Python パッケージはインポートしません。

### 開発

```bash
uv sync --locked
uv run python scripts/verify_all.py --stage fast
uv run python scripts/check_plugin_load.py
uv run python scripts/verify_all.py --stage standard
actionlint
uvx zizmor@1.30.1 --format plain .github/workflows
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
uv run python scripts/smoke_image.py --image sim-tools:local
```

実装・デプロイ境界は [operations](docs/operations.md)、
[architecture](docs/architecture.md)、[Docker notes](docker/README.md) を参照してください。

### ライセンス

BSD-3-Clause（`LICENSE` 参照）。第三者コンポーネントは
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に一覧があります。
