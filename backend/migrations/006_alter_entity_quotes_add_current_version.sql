-- up
alter table entity_quotes
    add column current_version_id uuid references quote_versions(id);

-- down
alter table entity_quotes
    drop column if exists current_version_id;
