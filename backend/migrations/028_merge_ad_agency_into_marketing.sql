-- up
-- 사용자 정정(2026-08-08): "광고대행"은 마케팅과 별개인 4번째 과업종류가 아니라 마케팅 안의
-- 한 상품 유형이다. v0.4에서 "5개 법인 공통 4개 과업종류(마케팅/광고대행/고객검증/시장검증)"로
-- 확정했던 부분 중 광고대행을 취소하고 마케팅에 흡수한다 (1.4 참고).
--
-- 기술적으로도 뒷받침됨: 테스티파이/썬데이워커의 "광고형 마케팅 대행"은 테스티파이 마케팅
-- 마스터 파일(templates/testify.xlsx, 시트 '마케팅')의 4개 블록 중 첫 블록(A15/rows 16-19)에
-- 정확히 맞고, 마이그레이션 010이 과거에 "실제 발급 이력이 없어" 시장검증 시트를 임시로
-- 재사용하도록 잘못 설정해 둔 것도 함께 바로잡는다(quote_templates에서 해당 행 자체를 삭제
-- — 더 이상 참조되지 않음). 블렌디드랩의 광고대행/마케팅 템플릿은 애초부터 동일 파일·시트를
-- 공유하고 있었다(010 참고).

-- 테스티파이/썬데이워커: "광고형 마케팅 대행"을 마케팅의 4번째 대안 상품으로 편입
update item_catalogs set task_type = '마케팅', alt_group = '광고형'
where task_type = '광고대행' and module_name = '광고형 마케팅 대행';

-- 블렌디드랩: 기존 4개 항목(모듈 구분 없이 항상 포함)을 하나의 대안 상품으로 묶고,
-- "Meta 광고 테스트 기획 및 운영"을 상호 배타적인 두 번째 대안 상품으로 편입
update item_catalogs set module_name = '온라인 마케팅 패키지', alt_group = '마케팅기본형'
where task_type = '마케팅' and module_name is null
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set task_type = '마케팅', alt_group = '단일광고형'
where task_type = '광고대행' and module_name is null
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- 더 이상 참조되지 않는 광고대행 전용 템플릿 설정 삭제 (5개 법인 전부 — 010에서 실제 샘플
-- 없이 임시로 만들어 둔 placeholder들이었다)
delete from quote_templates where task_type = '광고대행';

-- down
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_mapping)
select entity_id, '광고대행', module_name, storage_path, sheet_name, cell_mapping
from quote_templates where task_type = '마케팅' and module_name is null;

update item_catalogs set task_type = '광고대행', alt_group = null
where task_type = '마케팅' and alt_group in ('광고형', '단일광고형');

update item_catalogs set module_name = null, alt_group = null
where task_type = '마케팅' and alt_group = '마케팅기본형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
