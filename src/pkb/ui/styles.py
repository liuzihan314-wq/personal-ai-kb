"""Local visual system for the Streamlit knowledge-base workbench."""


THEME_CSS = """
<style>
:root {
    --pkb-bg: #f7f5f0;
    --pkb-surface: #fffdf9;
    --pkb-surface-soft: #f2eee8;
    --pkb-ink: #292530;
    --pkb-muted: #625d68;
    --pkb-line: #e8e2da;
    --pkb-dark: #25212d;
    --pkb-purple: #c7b8ff;
    --pkb-purple-deep: #6755bf;
    --pkb-yellow: #f3d68e;
    --pkb-blue: #b9dced;
    --pkb-pink: #efc6d6;
    --pkb-green: #b8d8c4;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--pkb-bg);
}

[data-testid="stHeader"] {
    background: transparent;
}

main .block-container {
    max-width: 1480px;
    padding: 2.1rem 3rem 4.5rem;
}

[data-testid="stSidebar"] {
    background: var(--pkb-dark);
}

[data-testid="stSidebar"] > div:first-child {
    background:
        radial-gradient(circle at 15% 8%, rgba(199, 184, 255, 0.2), transparent 24%),
        var(--pkb-dark);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] .stCaptionContainer,
[data-testid="stSidebar"] label {
    color: #fffdf9;
}

[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.12);
}

[data-testid="stSidebar"] code {
    color: #ded5ff;
    background: rgba(255, 255, 255, 0.08);
}

.pkb-sidebar-brand {
    padding: 0.55rem 0 1.15rem;
}

.pkb-sidebar-brand .pkb-mark {
    display: inline-grid;
    width: 2.55rem;
    height: 2.55rem;
    margin-right: 0.62rem;
    place-items: center;
    border: 1px solid rgba(255, 255, 255, 0.36);
    border-radius: 0.88rem;
    background: linear-gradient(145deg, #d9d0ff, #ad97ff 62%, #f3d68e);
    box-shadow: 0 0.55rem 1.15rem rgba(0, 0, 0, 0.24);
    color: var(--pkb-dark);
    font-size: 0.63rem;
    font-weight: 900;
    letter-spacing: 0.08em;
}

.pkb-sidebar-brand .pkb-brand-name {
    color: #fffdf9;
    font-size: 1.08rem;
    font-weight: 850;
    letter-spacing: -0.02em;
    vertical-align: middle;
}

.pkb-sidebar-eyebrow,
.pkb-kicker,
.pkb-section-index,
.pkb-card-kicker {
    font-size: 0.66rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

.pkb-sidebar-eyebrow {
    margin: 0.8rem 0 0.35rem;
    color: #d9d2e4;
}

.pkb-sidebar-copy {
    margin: 0;
    color: #e1dbe8;
    font-size: 0.82rem;
    line-height: 1.55;
}

.pkb-side-status {
    margin: 1.35rem 0 1.5rem;
    padding: 0.9rem 0.95rem;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 1rem;
    background: rgba(255, 255, 255, 0.1);
}

.pkb-side-status .pkb-status-dot {
    display: inline-block;
    width: 0.46rem;
    height: 0.46rem;
    margin-right: 0.38rem;
    border-radius: 50%;
    background: var(--pkb-green);
    box-shadow: 0 0 0 0.22rem rgba(184, 216, 196, 0.12);
}

.pkb-side-status strong {
    color: #fffdf9;
    font-size: 0.84rem;
}

.pkb-side-status p {
    margin: 0.48rem 0 0;
    color: #e1dbe8;
    font-size: 0.75rem;
    line-height: 1.45;
}

.pkb-side-label {
    margin: 0.8rem 0 0.4rem;
    color: #d9d2e4;
    font-size: 0.67rem;
    font-weight: 800;
    letter-spacing: 0.13em;
    text-transform: uppercase;
}

.pkb-side-flow {
    display: flex;
    gap: 0.55rem;
    align-items: center;
    padding: 0.46rem 0;
    color: #fffdf9;
    font-size: 0.86rem;
    font-weight: 650;
}

.pkb-side-flow span {
    display: inline-grid;
    width: 1.55rem;
    height: 1.55rem;
    place-items: center;
    border-radius: 0.5rem;
    color: var(--pkb-dark);
    font-size: 0.68rem;
    font-weight: 850;
}

[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid rgba(255, 255, 255, 0.24);
    border-radius: 0.9rem;
    background: #302a3e !important;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {
    color: #fffdf9;
    font-weight: 800;
}

[data-testid="stSidebar"] div[data-testid="stForm"] {
    margin-top: 0.25rem;
    padding: 0.85rem 0.9rem 0.25rem;
    border: 0;
    border-radius: 0;
    background: transparent !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] div[data-testid="stForm"] label,
[data-testid="stSidebar"] div[data-testid="stForm"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] div[data-testid="stForm"] [data-testid="stWidgetLabel"] * {
    color: #fffdf9 !important;
    font-weight: 750;
}

[data-testid="stSidebar"] [data-testid="stExpanderDetails"],
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] form {
    background: #302a3e !important;
}

[data-testid="stSidebar"] div[data-testid="stTextInput"] input,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    border-color: #d9d0e4;
    background: #fffdf9;
    color: #292530;
}

[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: #292530;
}

[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] button,
[data-testid="stSidebar"] div.stButton > button,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondaryFormSubmit"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
    border: 1px solid #d9d0e4;
    background: #fffdf9;
    color: #292530;
    font-weight: 850;
}

[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stSidebar"] div.stButton > button:hover,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
    border-color: #c7b8ff;
    background: #e5dfff;
    color: #241d34;
}

[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
    border-color: #c7b8ff;
    background: #c7b8ff;
    color: #241d34;
}

[data-testid="stSidebar"] button[data-testid="stBaseButton-secondaryFormSubmit"] {
    border-color: #c7b8ff;
    background: #c7b8ff;
    color: #241d34;
}

button[data-testid="stExpandSidebarButton"] {
    width: 2.8rem;
    height: 2.8rem;
    border: 1px solid #bfb1e7;
    border-radius: 0.85rem;
    background: #292530 !important;
    outline: 3px solid #fffdf9;
    outline-offset: 3px;
    box-shadow: 0 0.35rem 0.9rem rgba(41, 37, 48, 0.18);
    color: #fffdf9;
}

button[data-testid="stExpandSidebarButton"] span,
button[data-testid="stExpandSidebarButton"] svg {
    color: #fffdf9;
    fill: currentColor;
}

.pkb-side-flow:nth-child(4) span { background: var(--pkb-purple); }
.pkb-side-flow:nth-child(5) span { background: var(--pkb-blue); }
.pkb-side-flow:nth-child(6) span { background: var(--pkb-yellow); }
.pkb-side-flow:nth-child(7) span { background: var(--pkb-pink); }

.pkb-hero {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
    min-height: 265px;
    overflow: hidden;
    margin-bottom: 1.25rem;
    padding: 2.2rem 2.4rem;
    border: 1px solid rgba(41, 37, 48, 0.06);
    border-radius: 2rem;
    background:
        radial-gradient(circle at 88% 12%, rgba(255, 255, 255, 0.62), transparent 28%),
        linear-gradient(122deg, #d7caff 0%, #eee0ef 50%, #f6dda1 100%);
    box-shadow: 0 1rem 2.8rem rgba(68, 53, 82, 0.08);
}

.pkb-hero::after {
    position: absolute;
    right: -3.5rem;
    bottom: -5rem;
    width: 16rem;
    height: 16rem;
    border: 1px solid rgba(41, 37, 48, 0.08);
    border-radius: 50%;
    content: "";
}

.pkb-hero-copy {
    position: relative;
    z-index: 1;
    align-self: center;
    max-width: 680px;
}

.pkb-kicker {
    margin-bottom: 0.9rem;
    color: #6c5ba4;
}

.pkb-hero h1 {
    max-width: 700px;
    margin: 0;
    color: var(--pkb-ink);
    font-size: clamp(2.25rem, 4.2vw, 4.1rem);
    font-weight: 800;
    letter-spacing: -0.065em;
    line-height: 0.98;
}

.pkb-hero p {
    max-width: 590px;
    margin: 1.1rem 0 0;
    color: #5e5765;
    font-size: 1rem;
    line-height: 1.65;
}

.pkb-hero-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1.4rem;
}

.pkb-hero-tags span {
    padding: 0.42rem 0.72rem;
    border: 1px solid rgba(41, 37, 48, 0.1);
    border-radius: 999px;
    background: rgba(255, 253, 249, 0.48);
    color: #51495e;
    font-size: 0.72rem;
    font-weight: 700;
}

.pkb-hero-art {
    position: relative;
    min-height: 215px;
}

.pkb-orbit {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 205px;
    height: 205px;
    transform: translate(-38%, -50%) rotate(-18deg);
    border: 1px solid rgba(41, 37, 48, 0.18);
    border-radius: 50%;
}

.pkb-orbit::before,
.pkb-orbit::after {
    position: absolute;
    width: 2.1rem;
    height: 2.1rem;
    border-radius: 0.8rem;
    content: "";
}

.pkb-orbit::before {
    top: 0.65rem;
    right: 1.1rem;
    background: var(--pkb-pink);
}

.pkb-orbit::after {
    bottom: 0.35rem;
    left: 1.3rem;
    background: var(--pkb-blue);
}

.pkb-orbit-core {
    position: absolute;
    top: 50%;
    left: 50%;
    display: grid;
    width: 106px;
    height: 106px;
    place-items: center;
    transform: translate(-50%, -50%);
    border: 8px solid rgba(255, 253, 249, 0.58);
    border-radius: 2rem;
    background: var(--pkb-dark);
    box-shadow: 0 1rem 2.2rem rgba(41, 37, 48, 0.18);
    color: #fffdf9;
    font-size: 2.15rem;
}

.pkb-orbit-note {
    position: absolute;
    right: 0.2rem;
    bottom: 0.8rem;
    padding: 0.72rem 0.85rem;
    border: 1px solid rgba(41, 37, 48, 0.1);
    border-radius: 0.95rem;
    background: rgba(255, 253, 249, 0.62);
    color: #5d5563;
    font-size: 0.68rem;
    font-weight: 750;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.pkb-flow-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.8rem;
    margin-bottom: 2.55rem;
}

.pkb-flow-card {
    min-height: 113px;
    padding: 1rem 1.05rem;
    border: 1px solid var(--pkb-line);
    border-radius: 1.25rem;
    background: var(--pkb-surface);
}

.pkb-flow-card .pkb-flow-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--pkb-muted);
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.pkb-flow-card .pkb-flow-icon {
    display: inline-grid;
    width: 1.8rem;
    height: 1.8rem;
    place-items: center;
    border-radius: 0.65rem;
    color: var(--pkb-ink);
    font-size: 0.88rem;
    font-weight: 800;
}

.pkb-flow-card:nth-child(1) .pkb-flow-icon { background: var(--pkb-purple); }
.pkb-flow-card:nth-child(2) .pkb-flow-icon { background: var(--pkb-blue); }
.pkb-flow-card:nth-child(3) .pkb-flow-icon { background: var(--pkb-yellow); }
.pkb-flow-card:nth-child(4) .pkb-flow-icon { background: var(--pkb-pink); }

.pkb-flow-card h3 {
    margin: 0.78rem 0 0.25rem;
    color: var(--pkb-ink);
    font-size: 1rem;
    letter-spacing: -0.025em;
}

.pkb-flow-card p {
    margin: 0;
    color: var(--pkb-muted);
    font-size: 0.76rem;
    line-height: 1.4;
}

.pkb-section-head {
    display: flex;
    gap: 1rem;
    align-items: flex-start;
    margin: 0.3rem 0 1.2rem;
}

.pkb-section-index {
    display: inline-grid;
    flex: 0 0 auto;
    width: 2.6rem;
    height: 2.6rem;
    place-items: center;
    border-radius: 0.9rem;
    color: var(--pkb-ink);
    font-size: 0.68rem;
    letter-spacing: 0.03em;
}

.pkb-accent-purple .pkb-section-index { background: var(--pkb-purple); }
.pkb-accent-blue .pkb-section-index { background: var(--pkb-blue); }
.pkb-accent-yellow .pkb-section-index { background: var(--pkb-yellow); }
.pkb-accent-pink .pkb-section-index { background: var(--pkb-pink); }

.pkb-section-head h2 {
    margin: 0.18rem 0 0.28rem;
    color: var(--pkb-ink);
    font-size: clamp(1.55rem, 2.2vw, 2.25rem);
    font-weight: 800;
    letter-spacing: -0.055em;
    line-height: 1.05;
}

.pkb-section-head p {
    max-width: 760px;
    margin: 0;
    color: var(--pkb-muted);
    font-size: 0.88rem;
    line-height: 1.55;
}

.pkb-card-heading {
    margin-bottom: 1rem;
}

.pkb-card-heading .pkb-card-kicker,
.pkb-section-head .pkb-card-kicker {
    color: var(--pkb-muted);
}

.pkb-card-heading h3 {
    margin: 0.35rem 0 0.3rem;
    color: var(--pkb-ink);
    font-size: 1.28rem;
    font-weight: 800;
    letter-spacing: -0.04em;
}

.pkb-card-heading p {
    margin: 0;
    color: var(--pkb-muted);
    font-size: 0.8rem;
    line-height: 1.5;
}

[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stForm"] {
    border: 1px solid var(--pkb-line);
    border-radius: 1.45rem;
    background: var(--pkb-surface);
    box-shadow: 0 0.7rem 2rem rgba(47, 39, 53, 0.035);
}

[data-testid="stVerticalBlockBorderWrapper"] > div {
    gap: 0.7rem;
}

div[data-testid="stForm"] {
    padding: 1.15rem 1.25rem 0.35rem;
}

[data-testid="stMetric"] {
    padding: 0.72rem 0.82rem;
    border-radius: 0.9rem;
    background: var(--pkb-surface-soft);
}

[data-testid="stMetricLabel"] {
    color: var(--pkb-muted);
    font-size: 0.68rem;
    font-weight: 750;
}

[data-testid="stMetricValue"] {
    color: var(--pkb-ink);
    font-size: 1.05rem;
}

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input {
    border: 1px solid var(--pkb-line);
    border-radius: 0.85rem;
    background: #fffefa;
    color: var(--pkb-ink);
}

div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus,
div[data-testid="stNumberInput"] input:focus {
    border-color: var(--pkb-purple-deep);
    box-shadow: 0 0 0 0.18rem rgba(103, 85, 191, 0.12);
}

div[data-testid="stFileUploader"] section {
    border: 1px dashed #c9c0d5;
    border-radius: 1rem;
    background: #fbf9ff;
}

div[data-testid="stFileUploader"] section:hover {
    border-color: var(--pkb-purple-deep);
}

div[data-testid="stFormSubmitButton"] button,
div.stButton > button {
    min-height: 2.55rem;
    border-radius: 0.85rem;
    font-weight: 750;
    letter-spacing: -0.01em;
}

div[data-testid="stFormSubmitButton"] button[kind="primary"],
div.stButton > button[kind="primary"] {
    border-color: var(--pkb-dark);
    background: var(--pkb-dark);
    color: #fffdf9;
}

div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
div.stButton > button[kind="primary"]:hover {
    border-color: #40364d;
    background: #40364d;
    color: #fffdf9;
}

div[data-testid="stFormSubmitButton"] button:disabled,
div.stButton > button:disabled {
    border-color: #e5e0da;
    background: #eeeae4;
    color: #aaa3ac;
}

[data-baseweb="tab-list"] {
    gap: 0.35rem;
    margin: 0.25rem 0 1.8rem;
    padding: 0.36rem;
    border-radius: 1.25rem;
    background: var(--pkb-dark);
}

[data-baseweb="tab"] {
    min-height: 2.55rem;
    padding: 0.4rem 1rem;
    border-radius: 0.92rem;
    color: #bfb6c8;
    font-size: 0.82rem;
    font-weight: 700;
}

[data-baseweb="tab"] p {
    color: inherit;
}

[data-baseweb="tab"][aria-selected="true"] {
    background: #fffdf9;
    color: var(--pkb-ink);
}

[data-baseweb="tab-highlight"] {
    display: none;
}

[data-testid="stTabs"] [role="tablist"] {
    display: flex;
    gap: 0.35rem;
    margin: 0.25rem 0 1.8rem;
    padding: 0.36rem;
    border-radius: 1.25rem;
    background: var(--pkb-dark);
}

[data-testid="stTabs"] [data-testid="stTab"] {
    min-height: 2.55rem;
    padding: 0.4rem 1rem;
    border: 0;
    border-radius: 0.92rem;
    color: #bfb6c8;
    font-size: 0.82rem;
    font-weight: 700;
}

[data-testid="stTabs"] [data-testid="stTab"] [data-testid="stMarkdownContainer"] p {
    color: inherit;
}

[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
    background: #fffdf9;
    color: var(--pkb-ink);
}

[data-testid="stTabs"] .react-aria-SelectionIndicator {
    display: none;
}

.pkb-result-head {
    display: flex;
    gap: 1rem;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
}

.pkb-result-head h3 {
    margin: 0.5rem 0 0;
    color: var(--pkb-ink);
    font-size: 1.25rem;
    letter-spacing: -0.04em;
}

.pkb-status-pill {
    display: inline-flex;
    width: fit-content;
    align-items: center;
    padding: 0.35rem 0.62rem;
    border-radius: 999px;
    font-size: 0.67rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.pkb-status-success { background: #dfeee4; color: #397252; }
.pkb-status-neutral { background: #ede9e4; color: #6d6570; }
.pkb-status-pending { background: #fff0c9; color: #866a26; }
.pkb-status-confirmed { background: #e3ddff; color: #5f4da6; }

.pkb-result-count {
    flex: 0 0 auto;
    padding: 0.65rem 0.8rem;
    border-radius: 0.85rem;
    background: var(--pkb-surface-soft);
    color: var(--pkb-ink);
    font-size: 0.72rem;
    font-weight: 800;
    text-align: right;
}

.pkb-result-count small {
    display: block;
    margin-bottom: 0.2rem;
    color: var(--pkb-muted);
    font-size: 0.62rem;
    font-weight: 700;
}

.pkb-gate-card {
    margin: 1.1rem 0 0.75rem;
    padding: 1.15rem 1.25rem;
    border-radius: 1.2rem;
    background: var(--pkb-dark);
    color: #fffdf9;
}

.pkb-gate-card .pkb-card-kicker { color: #bfb6c8; }
.pkb-gate-card h3 { margin: 0.35rem 0 0.3rem; font-size: 1.06rem; }
.pkb-gate-card p { margin: 0; color: #c9c0d0; font-size: 0.8rem; line-height: 1.5; }

.pkb-source-heading {
    margin: 1.1rem 0 0.55rem;
    color: var(--pkb-ink);
    font-size: 0.76rem;
    font-weight: 850;
    letter-spacing: 0.09em;
    text-transform: uppercase;
}

.pkb-source-row {
    display: flex;
    gap: 0.6rem;
    align-items: baseline;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--pkb-line);
    color: var(--pkb-muted);
    font-size: 0.76rem;
    line-height: 1.45;
}

.pkb-source-row:last-child { border-bottom: 0; }
.pkb-source-row strong { color: var(--pkb-ink); font-weight: 750; }
.pkb-source-kind { color: var(--pkb-purple-deep); font-size: 0.66rem; font-weight: 850; text-transform: uppercase; }

div[data-testid="stExpander"] {
    border: 1px solid var(--pkb-line);
    border-radius: 1rem;
    background: #fffefa;
}

div[data-testid="stExpander"] summary:hover {
    background: #f8f5ef;
}

@media (max-width: 980px) {
    main .block-container { padding: 1.5rem 1.25rem 3.5rem; }
    .pkb-hero { grid-template-columns: minmax(0, 1fr) minmax(190px, 0.7fr); padding: 1.8rem; }
    .pkb-orbit { transform: translate(-50%, -50%) scale(0.82) rotate(-18deg); }
    .pkb-flow-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 680px) {
    main .block-container { padding: 1rem 0.8rem 2.7rem; }
    .pkb-hero { display: block; min-height: auto; padding: 1.55rem; border-radius: 1.45rem; }
    .pkb-hero h1 { font-size: 2.45rem; }
    .pkb-hero p { font-size: 0.88rem; }
    .pkb-hero-art { display: none; }
    .pkb-flow-grid { grid-template-columns: 1fr; gap: 0.6rem; margin-bottom: 1.9rem; }
    .pkb-flow-card { min-height: auto; }
    .pkb-section-head { gap: 0.7rem; }
    .pkb-section-index { width: 2.25rem; height: 2.25rem; border-radius: 0.72rem; }
    .pkb-section-head h2 { font-size: 1.7rem; }
    [data-baseweb="tab-list"],
    [data-testid="stTabs"] [role="tablist"] { overflow-x: auto; margin-bottom: 1.35rem; }
    [data-baseweb="tab"],
    [data-testid="stTabs"] [data-testid="stTab"] { flex: 0 0 auto; padding-inline: 0.8rem; white-space: nowrap; }
    [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 1.15rem; }
    .pkb-result-head { display: block; }
    .pkb-result-count { display: inline-block; margin-top: 0.75rem; text-align: left; }
}
</style>
"""


__all__ = ["THEME_CSS"]
