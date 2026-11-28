"""The parts of a project: one per table a change set can change (step 4c2).

A change set holds, for each part, a list of records. A record is one row in words: its row key names it by names and
codes, never by database ids (docs/rules/row-keys.md), and its other fields are the table's own column names. The
same record shape is what the web app shows, what a Run writes and what the VS Code snapshot holds.

Each part says, in data, how its records become rows:
- `key`: the columns that identify the row, each worked out from record fields by an SQL expression. Every key field
  is required. An expression that finds nothing (NULL) means the record names something unknown (CHANGE-SET-003).
- `refs`: other id columns worked out from names, such as a link's parent entity. Written only when their fields are
  in the record; a field given as null writes NULL.
- `values`: columns copied as they are, written only when the field is in the record. So a record that leaves a
  field out keeps the saved value, and a missing record changes nothing (design/vscode/bridge.md).
- `read`: the SQL that lists the project's saved rows as records, with the row's id as `id`.

`core/change_sets.py` does the rest the same way for every part. The parts are listed parents first, which is the
order Apply saves them in.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    name: str  # also the change set's column: f"{name}_document"
    table: str
    id_column: str
    key: dict  # column -> (record fields, SQL expression)
    values: tuple
    read: str
    refs: dict = None  # column -> (record fields, SQL expression)

    @property
    def key_fields(self):
        return tuple(field for fields, _ in self.key.values() for field in fields)

    @property
    def fields(self):
        return self.key_fields + tuple(f for fields, _ in (self.refs or {}).values() for f in fields) + self.values


def same(column, field):
    """Names compare like the ux_ indexes: upper and lower case and outer spaces are ignored."""
    return f"lower(btrim({column})) = lower(btrim(%({field})s))"


def scope_table(schema="object_schema", name="object_name"):
    """The id of the project's scope table with this schema and name (SCOPE-005 keeps the pair unique)."""
    return f"""(SELECT o.object_id FROM project.project_input_scope AS s JOIN core.object AS o USING (object_id)
                 WHERE s.project_id = %(project_id)s AND {same('o.object_schema', schema)} AND {same('o.object_name', name)}
                 ORDER BY s.is_active DESC, o.object_id LIMIT 1)"""


def column(table_sql, name="attribute_name"):
    return f"(SELECT a.attribute_id FROM core.attribute AS a WHERE a.object_id = {table_sql} AND {same('a.attribute_name', name)})"


def system(field="system_code"):
    return f"(SELECT system_id FROM core.system WHERE {same('system_code', field)})"


def entity(model, schema=None, name=None):
    schema, name = schema or f"{model}_entity_schema_name", name or f"{model}_entity_name"
    return f"""(SELECT e.{model}_entity_id FROM workflow.{model}_entity AS e WHERE e.project_id = %(project_id)s
                 AND {same(f'e.{model}_entity_schema_name', schema)} AND {same(f'e.{model}_entity_name', name)})"""


def attribute(model, entity_sql=None, name=None):
    name = name or f"{model}_attribute_name"
    return f"""(SELECT a.{model}_attribute_id FROM workflow.{model}_attribute AS a
                 WHERE a.{model}_entity_id = {entity_sql or entity(model)} AND {same(f'a.{model}_attribute_name', name)})"""


def mapping(model):
    return f"""(SELECT m.{model}_object_mapping_id FROM workflow.{model}_object_mapping AS m
                 WHERE m.{model}_entity_id = {entity(model)} AND m.system_id = {system()})"""


def code_file(model):
    return f"""(SELECT c.{model}_code_id FROM workflow.{model}_code AS c
                 WHERE c.{model}_entity_id = {entity(model)} AND {same(f'c.{model}_file_name', f'{model}_file_name')})"""


def validation_group(model):
    return f"""(SELECT g.{model}_validation_group_id FROM workflow.{model}_validation_group AS g
                 WHERE g.{model}_entity_id = {entity(model)} AND g.system_id = {system()})"""


PROJECT = ((), "%(project_id)s")
LOCK = ("is_locked", "is_active")

# The joins every read of an entity's rows uses: e is the entity.
TABLE_NAMES = "o.object_schema, o.object_name"


def _scope_parts():
    return [
        Part(
            "project_input_scope", "project.project_input_scope", "project_input_scope_id",
            key={"project_id": PROJECT,
                 "object_id": (("tenant_code", "system_code", "connection_code", "object_schema", "object_name"),
                               f"""(SELECT o.object_id FROM core.object AS o
                                     JOIN core.connection AS c USING (connection_id)
                                     JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id
                                     JOIN core.system AS sy ON sy.system_id = c.system_id
                                    WHERE {same('ct.tenant_code', 'tenant_code')} AND {same('sy.system_code', 'system_code')}
                                      AND {same('c.connection_code', 'connection_code')}
                                      AND {same('o.object_schema', 'object_schema')} AND {same('o.object_name', 'object_name')})""")},
            values=LOCK,
            read="""SELECT s.project_input_scope_id AS id, ct.tenant_code, sy.system_code, c.connection_code,
                           o.object_schema, o.object_name, s.is_locked, s.is_active
                      FROM project.project_input_scope AS s JOIN core.object AS o USING (object_id)
                      JOIN core.connection AS c ON c.connection_id = o.connection_id
                      JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id
                      JOIN core.system AS sy ON sy.system_id = c.system_id
                     WHERE s.project_id = %(project_id)s ORDER BY lower(o.object_schema), lower(o.object_name)""",
        ),
        Part(
            "attribute_profile", "workflow.attribute_profile", "attribute_profile_id",
            key={"project_id": PROJECT, "object_id": (("object_schema", "object_name"), scope_table()),
                 "attribute_id": (("attribute_name",), column(scope_table()))},
            values=("row_count", "non_null_count", "null_count", "blank_count", "distinct_count", "min_data_length",
                    "max_data_length", "avg_data_length", "percent_populated", "percent_duplicates", "percent_null",
                    "percent_blank", "percent_distinct", "sample_values", "is_active"),
            read=f"""SELECT p.attribute_profile_id AS id, {TABLE_NAMES}, a.attribute_name, p.row_count, p.non_null_count,
                            p.null_count, p.blank_count, p.distinct_count, p.min_data_length, p.max_data_length,
                            p.avg_data_length, p.percent_populated, p.percent_duplicates, p.percent_null,
                            p.percent_blank, p.percent_distinct, p.sample_values, p.is_active
                       FROM workflow.attribute_profile AS p JOIN core.object AS o USING (object_id)
                       JOIN core.attribute AS a USING (attribute_id)
                      WHERE p.project_id = %(project_id)s
                      ORDER BY lower(o.object_schema), lower(o.object_name), a.attribute_ordinal_position""",
        ),
        Part(
            "object_enrichment", "workflow.object_enrichment", "object_enrichment_id",
            key={"project_id": PROJECT, "object_id": (("object_schema", "object_name"), scope_table())},
            values=("object_definition", "object_grain") + LOCK,
            read=f"""SELECT e.object_enrichment_id AS id, {TABLE_NAMES}, e.object_definition, e.object_grain,
                            e.is_locked, e.is_active
                       FROM workflow.object_enrichment AS e JOIN core.object AS o USING (object_id)
                      WHERE e.project_id = %(project_id)s ORDER BY lower(o.object_schema), lower(o.object_name)""",
        ),
        Part(
            "attribute_enrichment", "workflow.attribute_enrichment", "attribute_enrichment_id",
            key={"project_id": PROJECT, "object_id": (("object_schema", "object_name"), scope_table()),
                 "attribute_id": (("attribute_name",), column(scope_table()))},
            values=("attribute_definition", "attribute_inferred_data_type", "is_natural_key", "is_surrogate_key",
                    "is_foreign_key_candidate", "is_nullable", "is_pii") + LOCK,
            read=f"""SELECT e.attribute_enrichment_id AS id, {TABLE_NAMES}, a.attribute_name, e.attribute_definition,
                            e.attribute_inferred_data_type, e.is_natural_key, e.is_surrogate_key,
                            e.is_foreign_key_candidate, e.is_nullable, e.is_pii, e.is_locked, e.is_active
                       FROM workflow.attribute_enrichment AS e JOIN core.object AS o USING (object_id)
                       JOIN core.attribute AS a USING (attribute_id)
                      WHERE e.project_id = %(project_id)s
                      ORDER BY lower(o.object_schema), lower(o.object_name), a.attribute_ordinal_position""",
        ),
        Part(
            "analysis_result", "workflow.analysis_result", "analysis_result_id",
            key={"project_id": PROJECT,
                 "from_object_id": (("from_object_schema", "from_object_name"),
                                    scope_table("from_object_schema", "from_object_name")),
                 "from_attribute_id": (("from_attribute_name",),
                                       column(scope_table("from_object_schema", "from_object_name"), "from_attribute_name")),
                 "to_object_id": (("to_object_schema", "to_object_name"),
                                  scope_table("to_object_schema", "to_object_name")),
                 "to_attribute_id": (("to_attribute_name",),
                                     column(scope_table("to_object_schema", "to_object_name"), "to_attribute_name"))},
            values=("relationship_kind", "inferred_cardinality", "validation_result",
                    "validation_source_non_null_count", "validation_source_distinct_count",
                    "validation_target_non_null_count", "validation_target_distinct_count",
                    "validation_source_missing_target_count", "validation_unused_target_count",
                    "validation_duplicate_target_key_count") + LOCK,
            read="""SELECT r.analysis_result_id AS id, fo.object_schema AS from_object_schema,
                           fo.object_name AS from_object_name, fa.attribute_name AS from_attribute_name,
                           tobj.object_schema AS to_object_schema, tobj.object_name AS to_object_name,
                           ta.attribute_name AS to_attribute_name, r.relationship_kind, r.inferred_cardinality,
                           r.validation_result, r.validation_source_non_null_count, r.validation_source_distinct_count,
                           r.validation_target_non_null_count, r.validation_target_distinct_count,
                           r.validation_source_missing_target_count, r.validation_unused_target_count,
                           r.validation_duplicate_target_key_count, r.is_locked, r.is_active
                      FROM workflow.analysis_result AS r
                      JOIN core.object AS fo ON fo.object_id = r.from_object_id
                      JOIN core.attribute AS fa ON fa.attribute_id = r.from_attribute_id
                      JOIN core.object AS tobj ON tobj.object_id = r.to_object_id
                      JOIN core.attribute AS ta ON ta.attribute_id = r.to_attribute_id
                     WHERE r.project_id = %(project_id)s
                     ORDER BY lower(fo.object_schema), lower(fo.object_name), lower(fa.attribute_name),
                              lower(tobj.object_schema), lower(tobj.object_name), lower(ta.attribute_name)""",
        ),
        Part(
            "context_group", "project.context_group", "context_group_id",
            key={"project_id": PROJECT,
                 "context_group_name": (("context_group_name",), "btrim(%(context_group_name)s)")},
            refs={"context_type_id": (("context_type_code",),
                                      f"(SELECT context_type_id FROM reference.context_type WHERE {same('context_type_code', 'context_type_code')})"),
                  "system_id": (("system_code",), system())},
            values=("context_group_description", "is_active"),
            read="""SELECT g.context_group_id AS id, g.context_group_name, t.context_type_code, s.system_code,
                           g.context_group_description, g.is_active
                      FROM project.context_group AS g JOIN reference.context_type AS t USING (context_type_id)
                      LEFT JOIN core.system AS s USING (system_id)
                     WHERE g.project_id = %(project_id)s ORDER BY lower(g.context_group_name)""",
        ),
        Part(
            "context_record", "project.context_record", "context_record_id",
            key={"context_group_id": (("context_group_name",),
                                      f"""(SELECT context_group_id FROM project.context_group
                                            WHERE project_id = %(project_id)s AND {same('context_group_name', 'context_group_name')})"""),
                 "context_record_number": (("context_record_number",), "%(context_record_number)s::int")},
            values=("context_record_text", "context_record_source_reference") + LOCK,
            read="""SELECT r.context_record_id AS id, g.context_group_name, r.context_record_number, r.context_record_text,
                           r.context_record_source_reference, r.is_locked, r.is_active
                      FROM project.context_record AS r JOIN project.context_group AS g USING (context_group_id)
                     WHERE g.project_id = %(project_id)s ORDER BY lower(g.context_group_name), r.context_record_number""",
        ),
        Part(
            "subject_area", "workflow.subject_area", "subject_area_id",
            key={"project_id": PROJECT, "subject_area_name": (("subject_area_name",), "btrim(%(subject_area_name)s)")},
            values=("subject_area_definition",) + LOCK,
            read="""SELECT subject_area_id AS id, subject_area_name, subject_area_definition, is_locked, is_active
                      FROM workflow.subject_area WHERE project_id = %(project_id)s ORDER BY lower(subject_area_name)""",
        ),
        Part(
            "subject_area_table", "workflow.subject_area_table", "subject_area_table_id",
            key={"subject_area_id": (("subject_area_name",),
                                     f"""(SELECT subject_area_id FROM workflow.subject_area
                                           WHERE project_id = %(project_id)s AND {same('subject_area_name', 'subject_area_name')})"""),
                 "object_id": (("object_schema", "object_name"), scope_table())},
            values=LOCK,
            read=f"""SELECT t.subject_area_table_id AS id, a.subject_area_name, {TABLE_NAMES}, t.is_locked, t.is_active
                       FROM workflow.subject_area_table AS t JOIN workflow.subject_area AS a USING (subject_area_id)
                       JOIN core.object AS o USING (object_id)
                      WHERE a.project_id = %(project_id)s
                      ORDER BY lower(a.subject_area_name), lower(o.object_schema), lower(o.object_name)""",
        ),
    ]


def _model_parts(model):
    """The parts of the Silver (operational) or Gold (dimensional) model, which have the same shape."""
    m = model
    ent = (f"{m}_entity_schema_name", f"{m}_entity_name")
    ent_key = {f"{m}_entity_id": (ent, entity(m))}
    ent_names = f"e.{m}_entity_schema_name, e.{m}_entity_name"
    ent_order = f"lower(e.{m}_entity_schema_name), lower(e.{m}_entity_name)"
    if m == "operational":
        entity_values = (f"{m}_entity_definition", f"{m}_entity_grain")
        type_ref = {f"{m}_entity_type_id": ((f"{m}_entity_type_code",),
                                             f"""(SELECT {m}_entity_type_id FROM reference.{m}_entity_type
                                                   WHERE {same(f'{m}_entity_type_code', f'{m}_entity_type_code')})""")}
        type_read, type_join = f"t.{m}_entity_type_code", f"LEFT JOIN reference.{m}_entity_type AS t USING ({m}_entity_type_id)"
        source_key = {"object_id": (("object_schema", "object_name"), scope_table())}
        source_read, source_join = TABLE_NAMES, "JOIN core.object AS o USING (object_id)"
        attr_source_key = {"attribute_id": (("object_schema", "object_name", "attribute_name"), column(scope_table()))}
        attr_source_read = f"{TABLE_NAMES}, sa.attribute_name"
        attr_source_join = "JOIN core.attribute AS sa ON sa.attribute_id = s.attribute_id JOIN core.object AS o ON o.object_id = sa.object_id"
    else:
        entity_values = (f"{m}_entity_type", f"{m}_entity_definition", f"{m}_entity_grain")
        type_ref, type_read, type_join = {}, f"e.{m}_entity_type", ""
        source_key = {"operational_entity_id": (("operational_entity_schema_name", "operational_entity_name"),
                                                entity("operational"))}
        source_read = "se.operational_entity_schema_name, se.operational_entity_name"
        source_join = "JOIN workflow.operational_entity AS se USING (operational_entity_id)"
        attr_source_key = {"operational_attribute_id": (
            ("operational_entity_schema_name", "operational_entity_name", "operational_attribute_name"),
            attribute("operational"))}
        attr_source_read = "se.operational_entity_schema_name, se.operational_entity_name, sa.operational_attribute_name"
        attr_source_join = """JOIN workflow.operational_attribute AS sa ON sa.operational_attribute_id = s.operational_attribute_id
                              JOIN workflow.operational_entity AS se ON se.operational_entity_id = sa.operational_entity_id"""
    attr_key = {f"{m}_attribute_id": (ent + (f"{m}_attribute_name",), attribute(m))}
    mapping_key = {f"{m}_object_mapping_id": (ent + ("system_code",), mapping(m))}
    group_key = {f"{m}_validation_group_id": (ent + ("system_code",), validation_group(m))}
    entity_join = f"JOIN workflow.{m}_entity AS e ON e.{m}_entity_id = a.{m}_entity_id"
    return [
        Part(
            f"{m}_entity", f"workflow.{m}_entity", f"{m}_entity_id",
            key={"project_id": PROJECT,
                 f"{m}_entity_schema_name": ((ent[0],), f"btrim(%({ent[0]})s)"),
                 f"{m}_entity_name": ((ent[1],), f"btrim(%({ent[1]})s)")},
            refs=type_ref,
            values=entity_values + (f"{m}_entity_dependency_order", "is_merged") + LOCK,
            read=f"""SELECT e.{m}_entity_id AS id, {ent_names}, {type_read} AS {m}_entity_type{'_code' if type_ref else ''},
                            {', '.join('e.' + v for v in entity_values if v != f'{m}_entity_type')},
                            e.{m}_entity_dependency_order, e.is_merged, e.is_locked, e.is_active
                       FROM workflow.{m}_entity AS e {type_join}
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}""",
        ),
        Part(
            f"{m}_attribute", f"workflow.{m}_attribute", f"{m}_attribute_id",
            key={f"{m}_entity_id": (ent, entity(m)),
                 f"{m}_attribute_name": ((f"{m}_attribute_name",), f"btrim(%({m}_attribute_name)s)")},
            values=(f"{m}_attribute_definition", f"{m}_attribute_data_type", f"{m}_attribute_ordinal_position",
                    "is_nullable", "is_surrogate_key", "is_natural_key") + LOCK,
            read=f"""SELECT a.{m}_attribute_id AS id, {ent_names}, a.{m}_attribute_name, a.{m}_attribute_definition,
                            a.{m}_attribute_data_type, a.{m}_attribute_ordinal_position, a.is_nullable,
                            a.is_surrogate_key, a.is_natural_key, a.is_locked, a.is_active
                       FROM workflow.{m}_attribute AS a {entity_join}
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, a.{m}_attribute_ordinal_position""",
        ),
        Part(
            f"{m}_entity_source", f"workflow.{m}_entity_source", f"{m}_entity_source_id",
            key={**ent_key, **source_key},
            values=(f"{m}_entity_source_note",) + LOCK,
            read=f"""SELECT s.{m}_entity_source_id AS id, {ent_names}, {source_read}, s.{m}_entity_source_note,
                            s.is_locked, s.is_active
                       FROM workflow.{m}_entity_source AS s JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                       {source_join}
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}""",
        ),
        Part(
            f"{m}_attribute_source", f"workflow.{m}_attribute_source", f"{m}_attribute_source_id",
            key={**attr_key, **attr_source_key},
            values=(f"{m}_attribute_source_note",) + LOCK,
            read=f"""SELECT s.{m}_attribute_source_id AS id, {ent_names}, a.{m}_attribute_name, {attr_source_read},
                            s.{m}_attribute_source_note, s.is_locked, s.is_active
                       FROM workflow.{m}_attribute_source AS s
                       JOIN workflow.{m}_attribute AS a ON a.{m}_attribute_id = s.{m}_attribute_id {entity_join}
                       {attr_source_join}
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, a.{m}_attribute_ordinal_position""",
        ),
        Part(
            f"{m}_link", f"workflow.{m}_link", f"{m}_link_id",
            key=attr_key,
            refs={f"parent_{m}_entity_id": ((f"parent_{m}_entity_schema_name", f"parent_{m}_entity_name"),
                                            entity(m, f"parent_{m}_entity_schema_name", f"parent_{m}_entity_name"))},
            values=LOCK,
            read=f"""SELECT l.{m}_link_id AS id, {ent_names}, a.{m}_attribute_name,
                            p.{m}_entity_schema_name AS parent_{m}_entity_schema_name,
                            p.{m}_entity_name AS parent_{m}_entity_name, l.is_locked, l.is_active
                       FROM workflow.{m}_link AS l JOIN workflow.{m}_attribute AS a USING ({m}_attribute_id)
                       {entity_join}
                       JOIN workflow.{m}_entity AS p ON p.{m}_entity_id = l.parent_{m}_entity_id
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, a.{m}_attribute_ordinal_position""",
        ),
        Part(
            f"{m}_object_mapping", f"workflow.{m}_object_mapping", f"{m}_object_mapping_id",
            key={**ent_key, "system_id": (("system_code",), system())},
            values=(f"{m}_object_mapping_tables", f"{m}_object_mapping_row_filter", f"{m}_object_mapping_sample_query",
                    f"{m}_object_mapping_transformation") + LOCK,
            read=f"""SELECT x.{m}_object_mapping_id AS id, {ent_names}, sy.system_code, x.{m}_object_mapping_tables,
                            x.{m}_object_mapping_row_filter, x.{m}_object_mapping_sample_query,
                            x.{m}_object_mapping_transformation, x.is_locked, x.is_active
                       FROM workflow.{m}_object_mapping AS x JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                       JOIN core.system AS sy USING (system_id)
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, sy.system_code""",
        ),
        Part(
            f"{m}_attribute_mapping", f"workflow.{m}_attribute_mapping", f"{m}_attribute_mapping_id",
            key={**mapping_key, f"{m}_attribute_id": ((f"{m}_attribute_name",), attribute(m))},
            values=(f"{m}_attribute_mapping_transformation",) + LOCK,
            read=f"""SELECT l.{m}_attribute_mapping_id AS id, {ent_names}, sy.system_code, a.{m}_attribute_name,
                            l.{m}_attribute_mapping_transformation, l.is_locked, l.is_active
                       FROM workflow.{m}_attribute_mapping AS l
                       JOIN workflow.{m}_object_mapping AS x USING ({m}_object_mapping_id)
                       JOIN workflow.{m}_attribute AS a ON a.{m}_attribute_id = l.{m}_attribute_id {entity_join}
                       JOIN core.system AS sy ON sy.system_id = x.system_id
                      WHERE e.project_id = %(project_id)s
                      ORDER BY {ent_order}, sy.system_code, a.{m}_attribute_ordinal_position""",
        ),
        Part(
            f"{m}_code", f"workflow.{m}_code", f"{m}_code_id",
            key={**ent_key, f"{m}_file_name": ((f"{m}_file_name",), f"btrim(%({m}_file_name)s)")},
            values=(f"{m}_code_text",) + LOCK,
            read=f"""SELECT c.{m}_code_id AS id, {ent_names}, c.{m}_file_name, c.{m}_code_text, c.is_locked, c.is_active
                       FROM workflow.{m}_code AS c JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, lower(c.{m}_file_name)""",
        ),
        Part(
            f"{m}_code_system", f"workflow.{m}_code_system", f"{m}_code_system_id",
            key={f"{m}_code_id": (ent + (f"{m}_file_name",), code_file(m)), "system_id": (("system_code",), system())},
            values=("is_active",),
            read=f"""SELECT cs.{m}_code_system_id AS id, {ent_names}, c.{m}_file_name, sy.system_code, cs.is_active
                       FROM workflow.{m}_code_system AS cs JOIN workflow.{m}_code AS c USING ({m}_code_id)
                       JOIN workflow.{m}_entity AS e ON e.{m}_entity_id = c.{m}_entity_id
                       JOIN core.system AS sy ON sy.system_id = cs.system_id
                      WHERE e.project_id = %(project_id)s ORDER BY {ent_order}, lower(c.{m}_file_name), sy.system_code""",
        ),
        Part(
            f"{m}_validation_group", f"workflow.{m}_validation_group", f"{m}_validation_group_id",
            key={"project_id": PROJECT, **ent_key, "system_id": (("system_code",), system())},
            values=(f"{m}_validation_group_description",) + LOCK,
            read=f"""SELECT g.{m}_validation_group_id AS id, {ent_names}, sy.system_code,
                            g.{m}_validation_group_description, g.is_locked, g.is_active
                       FROM workflow.{m}_validation_group AS g JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                       JOIN core.system AS sy ON sy.system_id = g.system_id
                      WHERE g.project_id = %(project_id)s ORDER BY {ent_order}, sy.system_code""",
        ),
        Part(
            f"{m}_validation_check", f"workflow.{m}_validation_check", f"{m}_validation_check_id",
            key={**group_key,
                 f"{m}_validation_check_name": ((f"{m}_validation_check_name",), f"btrim(%({m}_validation_check_name)s)")},
            values=(f"{m}_validation_check_description", "validation_category_code", "validation_severity",
                    "validation_query_sql", "validation_comparison_query_sql", "validation_result_data_type",
                    "validation_comparison_operator", "validation_comparison_value_type",
                    "validation_comparison_value") + LOCK,
            read=f"""SELECT c.{m}_validation_check_id AS id, {ent_names}, sy.system_code, c.{m}_validation_check_name,
                            c.{m}_validation_check_description, c.validation_category_code, c.validation_severity,
                            c.validation_query_sql, c.validation_comparison_query_sql, c.validation_result_data_type,
                            c.validation_comparison_operator, c.validation_comparison_value_type,
                            c.validation_comparison_value, c.is_locked, c.is_active
                       FROM workflow.{m}_validation_check AS c JOIN workflow.{m}_validation_group AS g USING ({m}_validation_group_id)
                       JOIN workflow.{m}_entity AS e ON e.{m}_entity_id = g.{m}_entity_id
                       JOIN core.system AS sy ON sy.system_id = g.system_id
                      WHERE g.project_id = %(project_id)s ORDER BY {ent_order}, sy.system_code, lower(c.{m}_validation_check_name)""",
        ),
    ]


PARTS = {part.name: part for part in _scope_parts() + _model_parts("operational") + _model_parts("dimensional")}
