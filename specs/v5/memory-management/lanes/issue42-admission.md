# Manual-memory credential admission — bounded controller contract

This necessary pre-activation correction implements design5.1 for the already approved manual remember/correct commands. It adds no database column, table, public request field, background job, classifier or model call. Scope stays owner-private; it does not authorize shared reuse.

Implement one neutral deterministic admission function used by BOTH MemoryCommands remember and correct before writing instruction/source/revision/operation payloads. Inspect the exact submitted content and every free-text conditions field; do not transform stored source text. Authorize the caller normally and preserve CAS/idempotency/receipt ordering. Rejection raises a stable MemoryError code `sensitive_content_unsupported`, with no matched value, digest or raw body in error/log/receipt. API will map this code to422 and allow the user to edit their own draft.

Supported positive rejection categories must be explicit, bounded and tested: private-key PEM blocks; credential-bearing authorization/cookie header values; clearly labeled password/API-key/access-token/refresh-token/secret assignments (including explicitly enumerated Chinese labels); password-bearing connection/URI strings; recognized provider-token/key shapes only where the pattern has an auditable definition. Keep rule inventory finite and in one module; do not add third-party scans, network calls or probabilistic sensitive-person inference. Negative instructions discussing credentials, public-key/certificate material, ordinary token counts and unrelated preferences are negative controls.

This is a conservative supported-pattern boundary, NOT a guarantee to discover every arbitrary secret, personal datum, obfuscated encoding or unlabeled value. Unsupported personal-data inference is not added. Ambiguous inferred long-term content remains excluded by provenance/admission paths; this validator must not claim to prove explicit confirmation or semantic truth. No newly rejected proposition is persisted as a candidate or failed-operation payload.

Original #42 developer owns NEW citeframe_memory/admission.py plus the smallest calls in existing commands.py, dedicated focused tests and a lane evidence section. No schema/migration/shared DTO/provider/compaction/API changes. Original Critical reviewer approves exact rule contract before affected product changes, then independently tests actual PostgreSQL no-write behavior and clean replay/CAS parity. Existing #43 does not own commands.py/admission.py. Management API consumes the accepted error after exact commit integration, and does not clone this validator.

## Exact finite policy candidate — pending original reviewer approval

Developer evidence proposal: ../evidence/issue42-admission-rules.md.
Proposal SHA-256: 35b19edf1889cb4ce37cad912154e50085f860e3141e87c348676cb1e2abf8fc.

The inventory and boundary fixture tables below are the exact candidate for R001 re-review. Approval applies only when explicitly recorded by the original reviewer against the refined contract hash. No product/test implementation is authorized by this pending appendix alone.

Scan content, conditions.subject and conditions.applicability independently. Keep exact submitted text unchanged. The proposal's input/result/ordering and false-positive limits are incorporated by the pinned hash above.

## Exact finite inventory proposed for approval

Rules search anywhere within each of the three fields. ASCII label/header matching is case-insensitive; token/key bodies remain case-sensitive. No casefolding or Unicode normalization of the input is performed. Horizontal whitespace means only ASCII space/tab; newline means CR or LF. Elsewhere, whitespace means Python str.isspace (Unicode whitespace). ASCII case-insensitive matching applies only to the stated labels, schemes and header names; no Unicode case equivalences are enabled. Quoted values terminate at the first matching quote; backslashes are literal characters, not escape syntax. Unpaired quotes do not form quoted values.

### R1: complete private-key PEM blocks

Match exact `-----BEGIN TYPE-----` / `-----END TYPE-----` pairs with the same TYPE and a non-whitespace body between them. Finite TYPE list: `PRIVATE KEY`, `RSA PRIVATE KEY`, `EC PRIVATE KEY`, `DSA PRIVATE KEY`, `OPENSSH PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`. Search spans newlines. Public-key and certificate BEGIN/END labels are excluded. Empty blocks or a bare/truncated marker are outside this rule.

### R2: credential-bearing headers

Header-name left boundary must not be an ASCII letter/digit/underscore/hyphen; separators are colon plus optional horizontal whitespace.

- `Authorization` or `Proxy-Authorization`: scheme `Bearer` or `Basic`, at least one horizontal space, then at least 8 ASCII characters from `[A-Za-z0-9._~+/-]` followed by optional `=` padding. The entire credential must end at whitespace, a quote, comma, semicolon or end-of-field. Scheme/body must be on one line. This is lexical validation, not base64/JWT verification.
- `Cookie` or `Set-Cookie`: a header value beginning with at least one cookie `name=value` pair. Name is `[A-Za-z0-9_.-]+`; value is a nonempty token excluding whitespace, semicolon, comma and quotes, or a matched single/double-quoted nonempty value without a newline. No whitespace is allowed between cookie name and equals or between equals and value. A bare cookie value ends at the first excluded character or end-of-field; no additional right boundary is required after a quoted value. No cookie name allowlist: ordinary cookies and session cookies share this grammar.

Actual syntactic header examples are rejected even when quoted in documentation. Mentioning headers without a concrete supported credential/value does not match.

### R3: clearly labeled assignments

A finite label, optional horizontal whitespace, followed by `=`, `:` or Chinese `：`, optional horizontal whitespace and an explicit value is rejected. Labels may have matching single/double quotes (JSON/config notation) or no quotes. Unquoted values are nonempty tokens excluding whitespace, comma, semicolon, braces, brackets and quotes; their right boundary must be end-of-field/newline/comma/semicolon/closing brace/closing bracket, allowing horizontal whitespace before that boundary. Matched single/double-quoted values may contain spaces but cannot contain a newline; they must be nonempty. No escape-sequence decoding is performed. A bare value may not begin with a quote. Quoted values require no additional right boundary after the closing quote. Left/right label boundaries exclude ASCII letters/digits/underscores to avoid matching a suffix inside another identifier.

English labels, ASCII case-insensitive, exhaustively:

- `password`, `passwd`, `pwd`, `secret`;
- `api_key`, `api-key`, `api key`, `apikey`;
- `access_token`, `access-token`, `access token`, `accesstoken`;
- `refresh_token`, `refresh-token`, `refresh token`, `refreshtoken`;
- `client_secret`, `client-secret`, `client secret`, `clientsecret`;
- `secret_key`, `secret-key`, `secret key`, `secretkey`;
- `private_key`, `private-key`, `private key`, `privatekey`;
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_TOKEN`, `GITLAB_TOKEN`, `DATABASE_PASSWORD`, `DB_PASSWORD`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`.

Chinese labels, exact spelling (the ASCII API letters remain case-insensitive): `密码`, `口令`, `API密钥`, `API 密钥`, `访问令牌`, `刷新令牌`, `客户端密钥`, `密钥`, `私钥`.

Standalone `token`, `tokens`, `令牌`, `公钥` and `证书` are not labels. Multiword discussion after a colon without a quoted value or terminated bare token is outside the assignment grammar. Literal assignments such as `password="example"`, `secret="birthday surprise"` and `密码：示例` are intentionally rejected because their syntax is indistinguishable from a submitted credential. There is no placeholder, negation or prose allowlist that can exempt an otherwise supported concrete match.

### R4: password-bearing URI authority

Recognized schemes, ASCII case-insensitive: `postgres`, `postgresql`, `postgresql+psycopg`, `mysql`, `mysql+pymysql`, `mongodb`, `mongodb+srv`, `redis`, `rediss`, `amqp`, `amqps`, `http`, `https`, `ftp`, `sftp`.

Match `scheme://username:password@host` with nonempty username, password and host. Username excludes whitespace and `/ : @ ? #`; password excludes whitespace and `/ @ ? #`; host excludes whitespace and `/ ? #` (literal spaces in these descriptions denote exclusions, not mandatory characters). Scheme left boundary excludes ASCII letters/digits/`+.-`. Percent escapes are recognized only as literal token characters, never decoded. Usernames without a password or with an empty password do not match. Other schemes, query-string credentials and DSN formats are not claimed by this URI rule; an independently matching labeled assignment still rejects.

### R5: explicitly bounded provider-style token shapes

These lexical definitions are the entire supported shape inventory; they do not verify issuance or promise coverage of every vendor version:

- GitHub classic family: `gh[pousr]_[A-Za-z0-9]{36}`.
- GitHub fine-grained shape: `github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}`.
- GitLab personal-access shape: `glpat-[A-Za-z0-9_-]{20}`.
- OpenAI-style prefix: `sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,256}`.

Each whole match has left/right boundaries excluding `[A-Za-z0-9_-]`; the implementation must not silently accept a truncated prefix of a longer token. Prefix/body case remains exact. AWS access-key IDs alone, arbitrary JWTs, arbitrary high-entropy strings and generic unlabeled tokens are excluded. Syntactically matching fake/sample/revoked values are rejected too.

## Boundary fixture inventory

The following are fixture generators, not executed tests. A*n means exactly n ASCII A characters; \n and \t mean a literal newline/tab. Interpolate each TYPE, LABEL, SCHEME, header or prefix over its exhaustive list above. Each expansion is a separate fixture, including all aliases, six PEM types, fifteen URI schemes, both authorization headers with both schemes, and both cookie headers. Positive fixtures reject; nearest negatives remain admitted unless another independently supported pattern is deliberately included.

| Stable rule ID | Parameter expansion | Synthetic positive | Nearest negative |
|---|---|---|---|
| R1 | Every private TYPE above | -----BEGIN TYPE-----\nQUJD\n-----END TYPE----- | -----BEGIN TYPE-----\n \t\n-----END TYPE----- |
| R2-auth | Authorization, Proxy-Authorization × Bearer, Basic | HEADER: SCHEME ABCDEFGH | HEADER: SCHEME ABCDEFG |
| R2-cookie-bare | Cookie, Set-Cookie | HEADER: session=synthetic | HEADER: session= |
| R2-cookie-single | Cookie, Set-Cookie | HEADER: session='synthetic value' | HEADER: session='' |
| R2-cookie-double | Cookie, Set-Cookie | HEADER: session="synthetic value" | HEADER: session="" |
| R3-bare | Every English and Chinese LABEL above × =, :, ： | LABEL=synthetic (substitute delimiter) | LABEL= (same delimiter, no value) |
| R3-single | Every LABEL above × all three delimiters | 'LABEL'='synthetic value' | 'LABEL'='' |
| R3-double | Every LABEL above × all three delimiters | "LABEL"="synthetic value" | "LABEL"="" |
| R4 | Every SCHEME above | SCHEME://demo:synthetic@localhost/db | SCHEME://demo:@localhost/db |
| R5-github-classic | Each prefix ghp_, gho_, ghu_, ghs_, ghr_ | PREFIX + A*36 | PREFIX + A*35 |
| R5-github-pat | Exact prefix | github_pat_ + A*22 + _ + A*59 | github_pat_ + A*22 + _ + A*58 |
| R5-gitlab | Exact prefix | glpat- + A*20 | glpat- + A*19 |
| R5-openai | sk-, sk-proj-, sk-svcacct- | PREFIX + A*32 | sk- + A*31 (shared lower-bound control) |

For R5-openai, the exact regex has an optional prefix group and a body alphabet containing hyphens. Consequently sk-proj- plus 31 A characters also matches the plain sk- alternative and rejects. Prefixes are not parsed as mutually exclusive formats. This overlap is part of the proposed lexical policy, not an authenticity determination. For each prefix, an overall token with 257 body characters after its optional prefix is overlong and admitted; no truncated substring may match.

Additional pinned boundary fixtures:

| Boundary | Reject | Admit |
|---|---|---|
| PEM type/case/pair | Complete RSA PRIVATE KEY with body QUJD | Complete PUBLIC KEY or CERTIFICATE with QUJD; lowercase private markers; mismatched BEGIN PRIVATE KEY / END RSA PRIVATE KEY; truncated BEGIN marker |
| Header casing | authorization:\tBEARER ABCDEFGH | X-Authorization: Bearer ABCDEFGH |
| Auth line/boundary/padding | Authorization: Basic QUJDREVGRw== | Authorization:\nBearer ABCDEFGH; Authorization: Bearer ABCDEFGH! |
| Cookie first pair | Cookie: theme=dark; session= | Cookie: empty=; session=synthetic |
| Assignment case/boundary | PASSWORD = synthetic; | my_password=synthetic; password_hint=synthetic |
| Assignment prose | password="example" | password: never store credentials |
| Assignment quoting | "api_key": "synthetic" | "api_key": ""; "api_key": "synthetic\nvalue" |
| Chinese assignment/discussion | 密码：示例 | 请勿保存密码或 API 密钥。; 令牌预算：4096 |
| Ordinary token controls | access_token=synthetic | token=4096; token budget: 4096; tokens: 2000 |
| URI casing/percent text | POSTGRESQL://demo:p%40ss@localhost/db | postgresql://demo@localhost/db; postgresql%3A%2F%2Fdemo%3Asynthetic%40localhost |
| URI scheme boundary | https://demo:synthetic@localhost | xhttps://demo:synthetic@localhost; sqlite://demo:synthetic@localhost |
| Provider full-token boundary | ghp_ + A*36 | ghp_ + A*37; xghp_ + A*36; GHP_ + A*36 |
| Provider upper bounds | sk-proj- + A*256 | sk-proj- + A*257; glpat- + A*21 |
| Negation has no exemption | Do not use Authorization: Bearer ABCDEFGH | Do not retain passwords, API keys or authorization headers. |
| Independent fields | One field contains password=synthetic | Content password, subject =synthetic, applicability project notes (no concatenation) |

These fixture tables define review inputs only. Runtime results, no-write evidence and implementation approval remain pending.
