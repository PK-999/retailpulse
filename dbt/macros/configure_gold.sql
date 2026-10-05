{% macro configure_gold() %}
    {% if target.type == 'databricks' %}
        {{ config(
            file_format='delta',
            incremental_strategy='merge',
            location_root=env_var(
                'RETAILPULSE_DBT_GOLD_LOCATION',
                'abfss://retailpulse@stretailpulsedevrp999.dfs.core.windows.net/gold/dbt'
            )
        ) }}
    {% endif %}
{% endmacro %}
