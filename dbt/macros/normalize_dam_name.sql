{% macro normalize_dam_name(column) %}
    case
        when {{ column }} = 'North Pine (Lake Samsonvale)' then 'North Pine'
        when {{ column }} = 'Lake Macdonald (Six Mile Creek)' then 'Lake Macdonald'
        when {{ column }} = 'Sideling Creek (Lake Kurwongbah)' then 'Sideling Creek'
        else {{ column }}
    end
{% endmacro %}
