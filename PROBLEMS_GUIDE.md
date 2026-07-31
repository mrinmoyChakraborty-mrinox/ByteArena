# Adding Problems & Testcases

BYTEARENA supports two ways to add problems to a contest: **manual entry** through the organizer UI, or **loading from disk** using the file-based layout.

---

## Method 1: Load from Disk (Recommended)

### Directory Structure

Place each problem in a subdirectory under `Contest/Problems/<code>/`:

```
Contest/
└── Problems/
    └── A/                      # <code> = "A"
        ├── statement.md        # Problem statement in Markdown
        ├── config.json         # Problem configuration (optional)
        └── tests/
            ├── input1.txt      # Testcase input
            ├── output1.txt     # Expected output
            ├── input2.txt
            ├── output2.txt
            └── ...
```

### `config.json`

Optional. Overrides defaults if present:

```json
{
  "title": "Two Sum",
  "time_limit_ms": 1000,
  "mem_limit_mb": 256,
  "points": 100
}
```

Defaults if `config.json` is absent:
| Field | Default |
|---|---|
| `title` | The directory code (e.g. `"A"`) |
| `time_limit_ms` | `1000` |
| `mem_limit_mb` | `256` |
| `points` | `100` |

### `statement.md`

The problem statement in Markdown format. This is what participants will see in the problem view screen.

### Testcases

Place input/output file pairs in the `tests/` directory. The loader auto-matches pairs by filename:

| Input file | Expected output file |
|---|---|
| `input1.txt` | `output1.txt` |
| `input2.txt` | `output2.txt` |
| `in1.txt` | `out1.txt` |
| `in1.txt` | `ans1.txt` |

Supported naming conventions:
- `input<N>.txt` / `output<N>.txt`
- `in<N>.txt` / `out<N>.txt`
- `in<N>.txt` / `ans<N>.txt`

### Loading via the UI

1. Go to the **Problems** tab in the organizer dashboard
2. Select the target contest
3. Click **Add Problem**
4. Switch to **Load from Disk** tab
5. Enter the problem code (e.g. `A`) — must match the directory name under `Contest/Problems/`
6. Click **Add**

The system reads `statement.md`, `config.json`, and all testcase files, then stores them in the database.

---

## Method 2: Manual Entry

1. Go to the **Problems** tab
2. Select the target contest
3. Click **Add Problem** → keep **Manual** tab selected
4. Fill in:
   - **Code** — short identifier (e.g. `A`, `B`, `C`)
   - **Title** — full problem name
   - **Statement** — problem description in Markdown
   - **Time/Memory/Points** — judge limits and score
5. Click **Add**

Testcases cannot be added through the manual UI yet — they are typically loaded from disk alongside the problem.

---

## Sample Problem

Create `Contest/Problems/A/config.json`:

```json
{
  "title": "Hello BYTEARENA",
  "time_limit_ms": 1000,
  "mem_limit_mb": 256,
  "points": 100
}
```

Create `Contest/Problems/A/statement.md`:

```markdown
# Hello BYTEARENA

Write a program that reads two integers **a** and **b** and prints their sum.

## Input Format
Two integers separated by a space.

## Output Format
A single integer — the sum of **a** and **b**.

## Constraints
- -10^9 ≤ a, b ≤ 10^9

## Sample Input
```
3 5
```

## Sample Output
```
8
```
```

Create testcases:

`Contest/Problems/A/tests/input1.txt`:
```
3 5
```

`Contest/Problems/A/tests/output1.txt`:
```
8
```

`Contest/Problems/A/tests/input2.txt`:
```
-10 20
```

`Contest/Problems/A/tests/output2.txt`:
```
10
```

`Contest/Problems/A/tests/input3.txt`:
```
100 200
```

`Contest/Problems/A/tests/output3.txt`:
```
300
```

Then load problem `A` from the organizer dashboard → Problems → Add Problem → Load from Disk.
