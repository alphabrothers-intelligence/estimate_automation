# Graph Report - /Users/a111-04-2310-01/Developer/data solution ax/estimate_automation  (2026-08-11)

## Corpus Check
- 11 files · ~46,944 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 560 nodes · 965 edges · 74 communities (53 shown, 21 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.78)
- Token cost: 138,669 input · 0 output

## Community Hubs (Navigation)
- PDF 렌더링 서비스 (openpyxl+LibreOffice)
- 견적 세트 API 라우터
- 카탈로그 모듈 옵션 API/모델
- FastAPI 앱 진입점 및 템플릿 라우터
- 프론트엔드 패키지 의존성
- 견적 마법사 UI (estimate-wizard.tsx)
- 실제 견적서 PDF 표본 (테스티파이/블렌디드랩)
- 카탈로그 항목배분 서비스
- 프론트엔드 TS 설정
- 실제 견적서 PDF 표본 (날짜·금액)
- 견적 목록 페이지 및 API 클라이언트
- 견적 상세/마법사 페이지
- DB 마이그레이션 (초기 테이블 생성)
- 핵심 데이터 모델 (EntityQuote/EstimateSet 등)
- PRD 문서 및 기술스택 결정
- PDF 생성 의존성 (FastAPI/LibreOffice)
- DB 마이그레이션 스크립트 (migrate.py)
- 템플릿 관리 페이지
- 앱 셸/네비게이션 레이아웃
- Supabase 연동 의존성
- 개발 서버 동시 실행 스크립트 (dev.sh)
- Anthropic Claude API 의존성
- 환경변수/커밋 규칙
- Next.js 프론트엔드 프레임워크
- Next.js 버전 경고 문서
- ESLint 설정
- Next.js 설정
- PostCSS 설정
- 마케팅 과업종류 통합 정정
- 에러 처리 규칙 (CLAUDE.md)
- PRD 기준 개발 규칙 (CLAUDE.md)
- 금지 사항 규칙 (CLAUDE.md)
- Next.js 기본 SVG 아이콘
- Next.js 기본 SVG 아이콘
- Next.js SVG 아이콘 안내
- Next.js 기본 SVG 아이콘
- Next.js 기본 SVG 아이콘
- 프로젝트 단위 견적 생성 (스케일업팀용, 추후 개발)
- 고객검증 과업종류
- AutoQuote SaaS v2.0 UI/UX 구상
- estimate_automation 프로젝트 소개

## God Nodes (most connected - your core abstractions)
1. `get_supabase()` - 34 edges
2. `_patch_xlsx()` - 16 edges
3. `compilerOptions` - 16 edges
4. `EstimateWizard()` - 15 edges
5. `handle()` - 14 edges
6. `EntityQuoteOut` - 12 edges
7. `edit_entity_quote()` - 12 edges
8. `_build_filled_xlsx()` - 12 edges
9. `CatalogItem` - 11 edges
10. `get_module_options()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `(테스티파이) 브릿지오 시장검증 견적서 — 인터뷰형 시장검증(FGI, 5,500,000원)` --semantically_similar_to--> `알파브라더스 4개 세부모듈(FGI/사용성테스트/기술성테스트/시장성테스트)`  [INFERRED] [semantically similar]
  data/(테스티파이) 브릿지오 시장검증 견적서_260616.pdf → 견적서_자동화_PRD_v0.1.md
- `(블렌디드랩) 고객검증 견적서_단아한화식 — PMF Survey+고객인터뷰(11,000,000원)` --shares_data_with--> `독립형 항목구성`  [INFERRED]
  data/(블렌디드랩) 고객검증 견적서_단아한화식_260202.pdf → 견적서_자동화_PRD_v0.1.md
- `02.(테스티파이) 미구 마케팅 견적서 — 그로스해킹 마케팅 대행(19,800,000원)` --shares_data_with--> `마케팅 ① 온라인광고/SEO/자사몰데이터세팅/그로스해킹 (개별 체크박스)`  [INFERRED]
  data/02. (테스티파이) 미구 마케팅 견적서_260324.pdf → 견적서_자동화_PRD_v0.1.md
- `(알파) 이루리랩스 UXUI디자인 견적서 — 알파브라더스 실제 디자인 발급 이력 1건(2,750,000원)` --shares_data_with--> `절삭/DC 목표총액 보정 메커니즘`  [AMBIGUOUS]
  data/(알파) 이루리랩스_UXUI디자인 견적서_250715_001.pdf → 견적서_자동화_PRD_v0.1.md
- `테스티파이 광고형 마케팅 대행 견적서 (미구, 2026-02-09, 16,500,000원)` --references--> `테스티파이 (계약법인)`  [EXTRACTED]
  data/02. (테스티파이) 미구 마케팅 대행 견적서_260211.pdf → 견적서_자동화_PRD_v0.1.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **5개 법인 모두 마케팅/고객검증/시장검증 3개 과업종류 공통 취급** — prd_v0_1_entity_testify, prd_v0_1_entity_alphabrothers, prd_v0_1_entity_blendedlab, prd_v0_1_entity_sundayworker, prd_v0_1_entity_abbg, prd_v0_1_task_marketing, prd_v0_1_task_customer_validation, prd_v0_1_task_market_validation [EXTRACTED 1.00]
- **견적서 자동화 시스템 핵심 데이터 모델 6개 테이블** — prd_v0_1_entity_template, prd_v0_1_quote_template, prd_v0_1_estimate_set, prd_v0_1_entity_quote, prd_v0_1_quote_version, prd_v0_1_item_catalog [EXTRACTED 1.00]
- **v0.8 시장검증 표준카탈로그 통합 결정의 근거가 된 실제 발급 자료** — prd_v0_1_market_validation_catalog_unification, prd_v0_1_alphabrothers_modules, data_02_testify_danahanhwasik_market_validation_estimate_02_260130, data_01_testify_migu_market_validation_estimate_260211 [INFERRED 0.75]
- **미구 마케팅 본견적/비교견적 발급 흐름** — prd_v0_1_migu_case, data_testify_migu_marketing_260324, data_blendedlab_marketing_migu_260424_rev, prd_v0_1_markup_policy [EXTRACTED 1.00]
- **단아한화식 고객검증(PMF) 본견적/비교견적 발급 흐름** — prd_v0_1_danahanhwasik_case, data_testify_danahanhwasik_market_validation_260130, data_blendedlab_customer_validation_danahanhwasik_260202, prd_v0_1_markup_policy [EXTRACTED 1.00]
- **FastAPI 채택 및 PDF 생성 기술 스택 (openpyxl+LibreOffice) 결정 클러스터** — claude_fastapi, claude_openpyxl, claude_libreoffice_headless, claude_pdf_generation_rationale [EXTRACTED 1.00]

## Communities (74 total, 21 thin omitted)

### Community 0 - "PDF 렌더링 서비스 (openpyxl+LibreOffice)"
Cohesion: 0.05
Nodes (70): _assign_groups_to_blocks(), _build_catalog_maps(), _build_cell_xml(), _build_filled_xlsx(), _cell_pattern(), _collapse_by_task_type(), _collect_header_updates(), _collect_item_block_updates() (+62 more)

### Community 1 - "견적 세트 API 라우터"
Cohesion: 0.08
Nodes (55): get_supabase(), EditRequest, EditResult, EntityQuoteOut, EntitySelectionIn, EstimateSetCreate, EstimateSetOut, EstimateSetSummary (+47 more)

### Community 2 - "카탈로그 모듈 옵션 API/모델"
Cohesion: 0.11
Nodes (31): CatalogModuleOptions, CatalogResult, EntityModuleOptions, EntityOption, ModuleGroup, ModuleItemGroup, ModuleOption, BaseModel (+23 more)

### Community 3 - "FastAPI 앱 진입점 및 템플릿 라우터"
Cohesion: 0.09
Nodes (27): health(), lifespan(), get, BaseModel, QuoteTemplateSummary, delete_template(), list_templates(), delete (+19 more)

### Community 4 - "프론트엔드 패키지 의존성"
Cohesion: 0.06
Nodes (32): eslint, eslint-config-next, dependencies, next, react, react-dom, devDependencies, eslint (+24 more)

### Community 5 - "견적 마법사 UI (estimate-wizard.tsx)"
Cohesion: 0.08
Nodes (21): ChatMessage, computeVatBreakdown(), DEFAULT_COLUMN_LABELS, DEFAULT_DETAIL_ORDER, EntitySelection, FIXED_TASK_TYPES, FixedTaskType, groupLineItems() (+13 more)

### Community 6 - "실제 견적서 PDF 표본 (테스티파이/블렌디드랩)"
Cohesion: 0.11
Nodes (31): 01.(테스티파이) 미구 시장검증 견적서 — 시장성테스트+설문형시장검증(16,500,000원), 02.(테스티파이) 단아한화식 시장검증 견적서 — Fake-door test형(8,052,000원), 02.(테스티파이) 미구 마케팅 대행 견적서 — 광고형 마케팅 대행(16,500,000원), 02.(테스티파이) 미구 마케팅 견적서 — 그로스해킹 마케팅 대행(19,800,000원), (알파) 이루리랩스 UXUI디자인 견적서 — 알파브라더스 실제 디자인 발급 이력 1건(2,750,000원), (블렌디드랩) 고객검증 견적서_단아한화식 — PMF Survey+고객인터뷰(11,000,000원), (블렌디드랩) 고객검증 견적서_미구 — 시장성테스트+설문형시장검증(20,900,000원), (블렌디드랩) 마케팅 견적서_미구 — 온라인/퍼포먼스/자사몰/그로스해킹(22,000,000원) (+23 more)

### Community 7 - "카탈로그 항목배분 서비스"
Cohesion: 0.14
Nodes (26): Anthropic, get_anthropic(), CatalogItem, allocate_items(), _allocate_single_group(), AllocatedItem, AllocationResult, _build_catalog_block() (+18 more)

### Community 8 - "프론트엔드 TS 설정"
Cohesion: 0.07
Nodes (28): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+20 more)

### Community 9 - "실제 견적서 PDF 표본 (날짜·금액)"
Cohesion: 0.14
Nodes (28): 인증 미도입 결정 (사용 인원 1인), 견적서 자동화 서비스 개요, 알파브라더스 UXUI디자인 견적서 (이루리랩스, 2025-07-15, 2,750,000원), 블렌디드랩 고객검증 견적서 (단아한화식, 2026-01-30, 11,000,000원), 블렌디드랩 고객검증 견적서 (미구, 2026-03-24, 20,900,000원), 블렌디드랩 마케팅 견적서 (미구, 2026-03-24, 22,000,000원), 테스티파이 시장검증(FGI) 견적서 (브릿지오, 2026-06-16, 5,500,000원), 테스티파이 시장검증(Fake-door형) 견적서 (단아한화식, 2026-01-30, 8,052,000원) (+20 more)

### Community 10 - "견적 목록 페이지 및 API 클라이언트"
Cohesion: 0.14
Nodes (18): EstimatesPage(), formatDate(), ApiError, CatalogModuleOptions, CreateEstimateSetInput, deleteEstimateSet(), EditResult, EntityModuleOptions (+10 more)

### Community 11 - "견적 상세/마법사 페이지"
Cohesion: 0.18
Nodes (15): emptyTasks(), EstimateWizard(), moduleNamesMatchingLabels(), selectedVariantLabels(), createEstimateSet(), editEntityQuote(), fetchCatalogModuleOptions(), fetchEntities() (+7 more)

### Community 12 - "DB 마이그레이션 (초기 테이블 생성)"
Cohesion: 0.18
Nodes (6): entity_templates, item_catalogs, estimate_sets, entity_quotes, quote_versions, quote_templates

### Community 13 - "핵심 데이터 모델 (EntityQuote/EstimateSet 등)"
Cohesion: 0.20
Nodes (12): 단계별 개발 프로세스 (Phase 1~8), 프로젝트 폴더 구조 (frontend/backend), 수정 범위 2단계 구분 (이번 견적만 vs 카탈로그 갱신), 과업종류 교차 선택 → 법인당 견적서 1건 병합 (v0.9), 직접 편집 대상 확장: 단가/작업일/투입인력/비고 (v0.7), EntityQuote (법인별 견적서), EntityTemplate (법인 참조 키), EstimateSet (견적 세트=사업 건) (+4 more)

### Community 14 - "PRD 문서 및 기술스택 결정"
Cohesion: 0.31
Nodes (11): 견적서 자동화 시스템 PRD (Draft v0.10), 채팅 기반 수정, 직접 편집, EntityQuote (데이터모델), EntityTemplate (데이터모델), EstimateSet (데이터모델), ItemCatalog (데이터모델), openpyxl+LibreOffice 원본파일 재사용 PDF 생성 방식 (+3 more)

### Community 15 - "PDF 생성 의존성 (FastAPI/LibreOffice)"
Cohesion: 0.22
Nodes (9): fastapi (python package), python-multipart, uvicorn[standard], FastAPI (백엔드), Gotenberg (동시변환 락 문제 시 검토할 대안 마이크로서비스), LibreOffice headless (xlsx→PDF 변환), openpyxl (마스터 xlsx 가변 셀 채우기), PDF 생성 방식 결정 근거 (원본 xlsx 재사용 + openpyxl/LibreOffice) (+1 more)

### Community 16 - "DB 마이그레이션 스크립트 (migrate.py)"
Cohesion: 0.50
Nodes (8): cmd_down(), cmd_status(), cmd_up(), ensure_migrations_table(), get_connection(), list_migration_files(), DB 마이그레이션 실행 스크립트 (up/down). 사용법: python scripts/migrate.py up # 아직 적용 안 된…, split_up_down()

### Community 17 - "템플릿 관리 페이지"
Cohesion: 0.39
Nodes (7): fileSize(), TemplateCard(), TemplatesPage(), deleteTemplate(), fetchTemplates(), QuoteTemplateSummary, replaceTemplate()

### Community 18 - "앱 셸/네비게이션 레이아웃"
Cohesion: 0.33
Nodes (3): AppShell(), navigation, metadata

### Community 19 - "Supabase 연동 의존성"
Cohesion: 0.50
Nodes (4): psycopg2-binary, supabase (python package), Supabase (PostgreSQL + Storage), supabase-py (ORM)

## Ambiguous Edges - Review These
- `썬데이워커 (법인)` → `8장 질문14: 법인별 실제 취급 과업 상충 이슈`  [AMBIGUOUS]
  견적서_자동화_PRD_v0.1.md · relation: conceptually_related_to
- `ABBG (법인)` → `8장 질문14: 법인별 실제 취급 과업 상충 이슈`  [AMBIGUOUS]
  견적서_자동화_PRD_v0.1.md · relation: conceptually_related_to
- `시장검증 (과업종류)` → `8장 질문14: 법인별 실제 취급 과업 상충 이슈`  [AMBIGUOUS]
  견적서_자동화_PRD_v0.1.md · relation: conceptually_related_to
- `절삭/DC 목표총액 보정 메커니즘` → `(알파) 이루리랩스 UXUI디자인 견적서 — 알파브라더스 실제 디자인 발급 이력 1건(2,750,000원)`  [AMBIGUOUS]
  data/(알파) 이루리랩스_UXUI디자인 견적서_250715_001.pdf · relation: shares_data_with

## Knowledge Gaps
- **106 isolated node(s):** `navigation`, `FIXED_TASK_TYPES`, `FixedTaskType`, `SCOPE_LABEL`, `ChatMessage` (+101 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `썬데이워커 (법인)` and `8장 질문14: 법인별 실제 취급 과업 상충 이슈`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `ABBG (법인)` and `8장 질문14: 법인별 실제 취급 과업 상충 이슈`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `시장검증 (과업종류)` and `8장 질문14: 법인별 실제 취급 과업 상충 이슈`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `절삭/DC 목표총액 보정 메커니즘` and `(알파) 이루리랩스 UXUI디자인 견적서 — 알파브라더스 실제 디자인 발급 이력 1건(2,750,000원)`?**
  _Edge tagged AMBIGUOUS (relation: shares_data_with) - confidence is low._
- **Why does `get_supabase()` connect `견적 세트 API 라우터` to `PDF 렌더링 서비스 (openpyxl+LibreOffice)`, `카탈로그 모듈 옵션 API/모델`, `FastAPI 앱 진입점 및 템플릿 라우터`, `카탈로그 항목배분 서비스`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `_build_filled_xlsx()` connect `PDF 렌더링 서비스 (openpyxl+LibreOffice)` to `견적 세트 API 라우터`?**
  _High betweenness centrality (0.005) - this node is a cross-community bridge._
- **What connects `navigation`, `FIXED_TASK_TYPES`, `FixedTaskType` to the rest of the system?**
  _106 weakly-connected nodes found - possible documentation gaps or missing edges._