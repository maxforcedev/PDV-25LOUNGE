from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cash', '0005_cash_session_cancellation')]

    operations = [
        migrations.RemoveConstraint(
            model_name='cashmovement',
            name='cash_movement_reason_not_empty',
        ),
        migrations.AlterField(
            model_name='cashmovement',
            name='reason',
            field=models.TextField(blank=True),
        ),
    ]
