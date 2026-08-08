-- up
-- 블렌디드랩 마스터가 구형 .xls(바이너리)라 zip/xml 직접 패치 방식으로 열 수 없어 PDF/xlsx
-- 발급이 막혀 있었다. LibreOffice headless로 1회 변환한 templates/blendedlab.xlsx로 교체한다
-- (로고·도장 이미지, 시트 이름("견적서 (2)", "견적서"), 수식 모두 보존 확인, 2026-07-10).
update quote_templates
set storage_path = 'templates/blendedlab.xlsx'
where storage_path = 'templates/blendedlab.xls';

-- down
update quote_templates
set storage_path = 'templates/blendedlab.xls'
where storage_path = 'templates/blendedlab.xlsx'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');