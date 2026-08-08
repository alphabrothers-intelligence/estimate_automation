-- up
-- 016에서 블렌디드랩 마케팅 비중을 채우려 했으나, 이 4개 행은 module_name이 아니라 item_name에
-- 카테고리명이 들어있어("온라인 마케팅" 등, module_name은 null) WHERE 조건이 매칭되지 않았다.
-- item_name 기준으로 다시 채운다.
update item_catalogs set historical_ratio = 20.0,
    standard_description = '마케팅 전략, USP설정, 소재 제작, Meta 운영'
where task_type = '마케팅' and item_name = '온라인 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 60.0,
    standard_description = '테크니컬 SEO, SEO키워드제안, 결과보고'
where task_type = '마케팅' and item_name = '퍼포먼스 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 10.0,
    standard_description = 'GA4, GTM, 대시보드 구축'
where task_type = '마케팅' and item_name = '자사몰 데이터 세팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 10.0,
    standard_description = '주간 단위 데이터분석 및 액션플랜'
where task_type = '마케팅' and item_name = '그로스해킹'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- down
update item_catalogs set historical_ratio = null, standard_description = '테스티파이 "온라인 광고" 미러링(압축)'
where task_type = '마케팅' and item_name = '온라인 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set historical_ratio = null, standard_description = '테스티파이 "SEO 마케팅" 미러링(압축). 재발급 시 "SEO 마케팅"으로 항목명이 바뀐 사례 있음'
where task_type = '마케팅' and item_name = '퍼포먼스 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set historical_ratio = null, standard_description = '테스티파이 항목명 그대로 사용'
where task_type = '마케팅' and item_name = '자사몰 데이터 세팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set historical_ratio = null, standard_description = '재발급 시 "자사몰 데이터 세팅"+"그로스해킹"이 "SNS 마케팅" 1개로 통합된 사례 있음'
where task_type = '마케팅' and item_name = '그로스해킹'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
