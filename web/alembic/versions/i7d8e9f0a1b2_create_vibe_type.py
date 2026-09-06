"""create vibe_type table and seed data

Revision ID: i7d8e9f0a1b2
Revises: h6c7d8e9f0a1
Create Date: 2026-09-06 10:00:00.000000

Replaces the free-text vibe_category column approach with a normalised
vibe_type lookup table. Six vibe themes are seeded matching VIBE_CATEGORIES
in synth/challenges.py; each row stores an llm_context field with the
comma-separated category list used to constrain challenge generation.
"""
import sqlalchemy as sa
from alembic import op

revision = "i7d8e9f0a1b2"
down_revision = "h6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vibe_type",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("llm_context", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_vibe_type_name"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO vibe_type (id, name, description, llm_context) VALUES
            (gen_random_uuid(), 'Здоровье и лёгкость', 'Здоровые и натуральные продукты', 'молочные продукты и яйца, овощи, фрукты, мясо и птица, рыба и морепродукты, орехи и сухофрукты'),
            (gen_random_uuid(), 'Экономия и запасы', 'Базовые продукты для экономных покупок и создания запасов', 'бакалея, консервация, масла и жиры, соусы и приправы'),
            (gen_random_uuid(), 'Побаловать себя', 'Сладости, снеки и напитки для удовольствия', 'кондитерка, сладости и снеки, напитки'),
            (gen_random_uuid(), 'Уют и порядок дома', 'Товары для дома и гигиены', 'товары для дома, бытовая химия, личная гигиена'),
            (gen_random_uuid(), 'Быстро и просто', 'Готовая еда и продукты для быстрого приготовления', 'готовая еда, хлеб и выпечка, заморозка'),
            (gen_random_uuid(), 'Забота о питомце', 'Товары для домашних животных', 'товары для животных')
            """
        )
    )


def downgrade() -> None:
    op.drop_table("vibe_type")
