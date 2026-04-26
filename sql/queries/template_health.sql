-- =====================================================================
-- template_health.sql
-- Delivery / read / reply funnel per WhatsApp template.
-- A sudden drop in delivery_rate often means the BSP flagged the template
-- or the Meta quality rating slipped.
-- =====================================================================
SELECT
    template_id,
    category,
    language,
    sent,
    delivered,
    read_count,
    replied,
    delivery_rate_pct,
    read_rate_pct,
    reply_rate_pct,
    CASE
        WHEN delivery_rate_pct < 85 THEN 'INVESTIGATE'
        WHEN read_rate_pct     < 40 THEN 'REVIEW_COPY'
        ELSE 'HEALTHY'
    END AS status_flag
FROM v_template_health
ORDER BY sent DESC;
