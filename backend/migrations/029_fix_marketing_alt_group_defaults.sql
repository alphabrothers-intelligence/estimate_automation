-- up
-- 028에서 놓친 버그 2건을 바로잡는다 (get_module_options로 직접 확인해서 발견):
--
-- 1. "광고형"(테스티파이/썬데이워커)이 여전히 is_required=true라, 원래 기본값이었던
--    "그로스해킹형"과 함께 대안 그룹 안에 기본값이 2개가 되어버렸다(둘 다 default=True로 뜸).
--    상호 배타 그룹은 기본값이 정확히 하나여야 하므로 "광고형"은 false로 내린다.
update item_catalogs set is_required = false
where task_type = '마케팅' and alt_group = '광고형';

-- 2. 블렌디드랩 "Meta 광고 테스트 기획 및 운영"(alt_group='단일광고형')에 module_name이 여전히
--    null로 남아있었다. get_module_options는 module_name이 있어야만 alt_group 로직을 적용하므로,
--    null인 채로는 "모듈 구분 없는 항목"으로 취급되어 어떤 대안을 고르든 항상 추가로 끼어든다.
--    module_name을 채워 다른 alt_group 상품과 동일하게 상호 배타적으로 만들고, 새 기본값
--    충돌을 막기 위해 is_required도 false로 내린다(기본값은 "마케팅기본형" 그대로 유지).
update item_catalogs set module_name = 'Meta 광고 테스트 기획 및 운영', is_required = false
where task_type = '마케팅' and alt_group = '단일광고형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- down
update item_catalogs set is_required = true
where task_type = '마케팅' and alt_group = '광고형';

update item_catalogs set module_name = null, is_required = true
where task_type = '마케팅' and alt_group = '단일광고형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
