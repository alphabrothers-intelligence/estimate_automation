-- up
insert into entity_templates (name) values
('테스티파이'),
('블렌디드랩'),
('알파브라더스'),
('썬데이워커'),
('ABBG');

-- down
delete from entity_templates
where name in ('테스티파이', '블렌디드랩', '알파브라더스', '썬데이워커', 'ABBG');
