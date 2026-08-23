# 견적서 자동화 백엔드 — FastAPI + LibreOffice headless
#
# 이 이미지에서 제일 까다로운 건 한글 글꼴이다. 마스터 xlsx가 지정한 글꼴이 없으면 LibreOffice가
# 제멋대로 대체해 한글이 □□□로 나오거나 자간이 달라져 표가 어긋난다. 로컬 맥에서 잘 나오는 건
# 시스템에 글꼴이 다 깔려 있어서일 뿐이다.
#
# 마스터 5종이 실제로 쓰는 글꼴(2026-08-21 집계):
#   맑은 고딕 46 · 나눔고딕 12 · 나눔고딕 ExtraBold 6 · 나눔스퀘어(_ac) 계열 13
#   Pretendard Light/SemiBold/ExtraBold 14 · 굴림체 3 · Arial 3 · Arial Unicode MS 1
# 이 중 맑은 고딕·굴림체·Arial 계열은 MS/Monotype 독점이라 재배포할 수 없다. 설치할 수 있는 건
# 설치하고, 못 하는 건 아래 fonts-local.conf에서 자유 글꼴로 치환한다.

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app

# libreoffice-calc만 넣는다(전체 libreoffice는 Writer/Impress까지 끌고 와 이미지가 3배가 된다).
# procps는 pdf_service가 리스너를 정리할 때 쓰는 pkill 때문에 필요하다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        procps \
        fontconfig \
        fonts-nanum \
        fonts-nanum-extra \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        fonts-liberation \
        curl \
        unzip \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Pretendard(OFL) — ABBG 양식이 쓴다. apt에 없어 공식 릴리스에서 받는다.
# 받기에 실패하면 빌드를 세운다 — 조용히 대체 글꼴로 넘어가면 배포 후에야 알게 된다.
RUN curl -fsSL -o /tmp/pretendard.zip \
        https://github.com/orioncactus/pretendard/releases/download/v1.3.9/Pretendard-1.3.9.zip \
    && unzip -q -j /tmp/pretendard.zip 'public/static/Pretendard-*.otf' -d /usr/share/fonts/opentype/pretendard \
    && rm /tmp/pretendard.zip \
    && fc-cache -f

# 로케일. LibreOffice는 날짜 칸을 로케일 기준으로 그린다 — 기본 C.UTF-8이면 견적일자가
# "8/21/2026"(미국식)으로 나간다. 맥에서는 ko_KR이라 "2026-08-21"이었다(2026-08-23 컨테이너
# 검증에서 발견). 고객에게 그대로 나가는 값이라 반드시 맞춰야 한다.
RUN apt-get update && apt-get install -y --no-install-recommends locales \
    && sed -i '/^# *ko_KR.UTF-8 UTF-8/s/^# *//' /etc/locale.gen \
    && locale-gen ko_KR.UTF-8 \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=ko_KR.UTF-8 \
    LANGUAGE=ko_KR:ko \
    LC_ALL=ko_KR.UTF-8

COPY fonts-local.conf /etc/fonts/local.conf
RUN fc-cache -f

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
# templates/는 넣지 않는다 — 런타임은 Supabase Storage에서 마스터를 받는다(template_storage.download).

# LibreOffice는 쓰기 가능한 HOME이 있어야 프로필을 만든다. root로 돌리지 않는다.
RUN useradd --create-home --home-dir /home/app app && chown -R app:app /app /home/app
USER app

# 플랫폼(Render/Railway/Fly)이 $PORT를 넣어준다. 없으면 8001.
ENV PORT=8001
EXPOSE 8001
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]