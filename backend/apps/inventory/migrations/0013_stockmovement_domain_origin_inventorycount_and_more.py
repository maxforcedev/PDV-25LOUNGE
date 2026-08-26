import django.db.models.deletion
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0031_v2_5_inventory_permissions'),
        ('inventory', '0012_stockmovement_unit_cost_snapshot'),
        ('products', '0007_alter_product_inventory_behavior'),
        ('sales', '0013_localize_payment_method_names'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='domain_origin',
            field=models.CharField(choices=[('LEGACY', 'Legado'), ('MANUAL', 'Movimentacao manual'), ('PURCHASE', 'Recebimento de compra'), ('TRANSFER_DISPATCH', 'Despacho de transferencia'), ('TRANSFER_RECEIPT', 'Recebimento de transferencia'), ('TRANSFER_RETURN', 'Retorno de transferencia'), ('TRANSFER_CORRECTION', 'Correcao de transferencia'), ('LOSS', 'Registro de perda'), ('INVENTORY_COUNT', 'Contagem de inventario')], default='LEGACY', editable=False, max_length=32),
        ),
        migrations.CreateModel(
            name='InventoryCount',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('OPEN', 'Aberto'), ('CONFIRMED', 'Confirmado')], default='OPEN', max_length=12)),
                ('observation', models.TextField()),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('confirmation_idempotency_key', models.UUIDField(blank=True, editable=False, null=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_counts', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_counts', to='companies.company')),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='confirmed_inventory_counts', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_inventory_counts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', '-id'),
            },
        ),
        migrations.CreateModel(
            name='InventoryCountItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('theoretical_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('counted_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('difference_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('counted_at', models.DateTimeField()),
                ('unit_cost_snapshot', models.DecimalField(decimal_places=12, max_digits=28)),
                ('sale_price_snapshot', models.DecimalField(decimal_places=2, max_digits=12)),
                ('cost_impact', models.DecimalField(decimal_places=12, max_digits=30)),
                ('potential_sale_value', models.DecimalField(decimal_places=12, max_digits=30)),
                ('observation', models.TextField(blank=True)),
                ('counted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_count_items', to=settings.AUTH_USER_MODEL)),
                ('inventory_count', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='inventory.inventorycount')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_count_items', to='products.product')),
            ],
            options={
                'ordering': ('product__name', 'id'),
            },
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='inventory_count_item',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.inventorycountitem'),
        ),
        migrations.CreateModel(
            name='LossRecord',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('idempotency_key', models.UUIDField(editable=False)),
                ('payload_fingerprint', models.CharField(editable=False, max_length=64)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('reason', models.CharField(choices=[('BREAKAGE', 'Quebra'), ('EXPIRATION', 'Vencimento'), ('DAMAGE', 'Avaria'), ('INTERNAL_USE', 'Consumo interno'), ('MISPLACEMENT', 'Extravio'), ('OPERATIONAL_ERROR', 'Erro operacional'), ('OTHER', 'Outro')], max_length=24)),
                ('observation', models.TextField()),
                ('unit_cost_snapshot', models.DecimalField(decimal_places=12, max_digits=28)),
                ('sale_price_snapshot', models.DecimalField(decimal_places=2, max_digits=12)),
                ('cost_impact', models.DecimalField(decimal_places=12, max_digits=30)),
                ('potential_sale_value', models.DecimalField(decimal_places=12, max_digits=30)),
                ('recorded_at', models.DateTimeField()),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_losses', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_losses', to='companies.company')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_losses', to='products.product')),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recorded_inventory_losses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-recorded_at', '-id'),
            },
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='loss_record',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.lossrecord'),
        ),
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('DRAFT', 'Rascunho'), ('IN_TRANSIT', 'Em transito'), ('PARTIALLY_RECEIVED', 'Recebida parcialmente'), ('RECEIVED', 'Recebida'), ('RECEIVED_WITH_DIVERGENCE', 'Recebida com divergencia'), ('CANCELLED', 'Cancelada')], default='DRAFT', max_length=32)),
                ('notes', models.TextField(blank=True)),
                ('dispatched_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancellation_reason', models.TextField(blank=True)),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancelled_stock_transfers', to=settings.AUTH_USER_MODEL)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_transfers', to='companies.company')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_stock_transfers', to=settings.AUTH_USER_MODEL)),
                ('destination_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incoming_stock_transfers', to='companies.branch')),
                ('dispatched_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='dispatched_stock_transfers', to=settings.AUTH_USER_MODEL)),
                ('origin_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='outgoing_stock_transfers', to='companies.branch')),
            ],
            options={
                'ordering': ('-created_at', '-id'),
            },
        ),
        migrations.CreateModel(
            name='StockTransferItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('requested_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('dispatched_quantity', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ('origin_unit_cost_snapshot', models.DecimalField(blank=True, decimal_places=12, max_digits=28, null=True)),
                ('origin_cost_source', models.CharField(blank=True, choices=[('BRANCH_AVERAGE', 'Custo medio da filial'), ('PRODUCT_FALLBACK', 'Fallback do produto')], max_length=24)),
                ('origin_sale_price_snapshot', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('product_name_snapshot', models.CharField(max_length=200)),
                ('product_internal_code_snapshot', models.CharField(max_length=100)),
                ('product_unit_snapshot', models.CharField(max_length=5)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_transfer_items', to='products.product')),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='inventory.stocktransfer')),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='transfer_item',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.stocktransferitem'),
        ),
        migrations.CreateModel(
            name='StockTransferReceipt',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('idempotency_key', models.UUIDField(editable=False)),
                ('payload_fingerprint', models.CharField(editable=False, max_length=64)),
                ('payload', models.JSONField(default=dict, editable=False)),
                ('finalize', models.BooleanField(default=False, editable=False)),
                ('notes', models.TextField(blank=True)),
                ('received_at', models.DateTimeField()),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_transfer_receipts', to='companies.company')),
                ('destination_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_transfer_receipts', to='companies.branch')),
                ('received_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='received_stock_transfers', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receipts', to='inventory.stocktransfer')),
            ],
            options={
                'ordering': ('-received_at', '-created_at'),
            },
        ),
        migrations.CreateModel(
            name='StockTransferReceiptItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dispatched_quantity_snapshot', models.DecimalField(decimal_places=3, max_digits=14)),
                ('previously_received_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('received_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('accumulated_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('pending_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('unit_cost_snapshot', models.DecimalField(decimal_places=12, max_digits=28)),
                ('receipt', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='inventory.stocktransferreceipt')),
                ('transfer_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receipt_items', to='inventory.stocktransferitem')),
            ],
            options={
                'ordering': ('transfer_item_id', 'id'),
            },
        ),
        migrations.CreateModel(
            name='TransferDivergence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dispatched_quantity_snapshot', models.DecimalField(decimal_places=3, max_digits=14)),
                ('received_quantity_snapshot', models.DecimalField(decimal_places=3, max_digits=14)),
                ('initial_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('resolved_quantity', models.DecimalField(decimal_places=3, default=Decimal('0'), max_digits=14)),
                ('pending_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('status', models.CharField(choices=[('PENDING', 'Pendente'), ('RESOLVED', 'Resolvida')], default='PENDING', max_length=10)),
                ('detected_at', models.DateTimeField()),
                ('detected_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='detected_transfer_divergences', to=settings.AUTH_USER_MODEL)),
                ('transfer_item', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='divergence', to='inventory.stocktransferitem')),
            ],
            options={
                'ordering': ('-detected_at', '-id'),
            },
        ),
        migrations.CreateModel(
            name='TransferDivergenceResolution',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('idempotency_key', models.UUIDField(editable=False)),
                ('payload_fingerprint', models.CharField(editable=False, max_length=64)),
                ('resolution_type', models.CharField(choices=[('FOUND_RECEIPT', 'Item localizado e recebido'), ('RETURN_TO_ORIGIN', 'Retorno confirmado a origem'), ('LOSS_IN_TRANSIT', 'Perda em transito'), ('AUTHORIZED_CORRECTION', 'Correcao autorizada de separacao')], max_length=32)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('observation', models.TextField()),
                ('resolved_at', models.DateTimeField()),
                ('divergence', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='resolutions', to='inventory.transferdivergence')),
                ('resolved_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfer_divergence_resolutions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('resolved_at', 'id'),
            },
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='transfer_resolution',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.transferdivergenceresolution'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.UniqueConstraint(condition=models.Q(('loss_record__isnull', False)), fields=('loss_record',), name='inventory_movement_loss_record_unique'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.UniqueConstraint(condition=models.Q(('inventory_count_item__isnull', False)), fields=('inventory_count_item',), name='inventory_movement_count_item_unique'),
        ),
        migrations.AddConstraint(
            model_name='inventorycount',
            constraint=models.UniqueConstraint(condition=models.Q(('confirmation_idempotency_key__isnull', False)), fields=('branch', 'confirmation_idempotency_key'), name='inventory_count_confirmation_idempotency_unique'),
        ),
        migrations.AddConstraint(
            model_name='inventorycountitem',
            constraint=models.UniqueConstraint(fields=('inventory_count', 'product'), name='inventory_count_product_unique'),
        ),
        migrations.AddConstraint(
            model_name='inventorycountitem',
            constraint=models.CheckConstraint(condition=models.Q(('counted_quantity__gte', 0), ('unit_cost_snapshot__gte', 0), ('sale_price_snapshot__gte', 0)), name='inventory_count_item_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='lossrecord',
            constraint=models.UniqueConstraint(fields=('branch', 'idempotency_key'), name='inventory_loss_idempotency_unique'),
        ),
        migrations.AddConstraint(
            model_name='lossrecord',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0), ('unit_cost_snapshot__gte', 0), ('sale_price_snapshot__gte', 0), ('cost_impact__gte', 0), ('potential_sale_value__gte', 0)), name='inventory_loss_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='stocktransfer',
            constraint=models.CheckConstraint(condition=models.Q(('origin_branch', models.F('destination_branch')), _negated=True), name='inventory_transfer_distinct_branches'),
        ),
        migrations.AddConstraint(
            model_name='stocktransferitem',
            constraint=models.UniqueConstraint(fields=('transfer', 'product'), name='inventory_transfer_product_unique'),
        ),
        migrations.AddConstraint(
            model_name='stocktransferitem',
            constraint=models.CheckConstraint(condition=models.Q(('requested_quantity__gt', 0), models.Q(('dispatched_quantity__isnull', True), ('dispatched_quantity__gt', 0), _connector='OR'), models.Q(('origin_unit_cost_snapshot__isnull', True), ('origin_unit_cost_snapshot__gte', 0), _connector='OR'), models.Q(('origin_sale_price_snapshot__isnull', True), ('origin_sale_price_snapshot__gte', 0), _connector='OR')), name='inventory_transfer_item_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='stocktransferreceipt',
            constraint=models.UniqueConstraint(fields=('destination_branch', 'idempotency_key'), name='inventory_transfer_receipt_idempotency_unique'),
        ),
        migrations.AddConstraint(
            model_name='stocktransferreceiptitem',
            constraint=models.UniqueConstraint(fields=('receipt', 'transfer_item'), name='inventory_transfer_receipt_item_unique'),
        ),
        migrations.AddConstraint(
            model_name='stocktransferreceiptitem',
            constraint=models.CheckConstraint(condition=models.Q(('dispatched_quantity_snapshot__gt', 0), ('previously_received_quantity__gte', 0), ('received_quantity__gt', 0), ('accumulated_quantity__gt', 0), ('pending_quantity__gte', 0), ('unit_cost_snapshot__gte', 0)), name='inventory_transfer_receipt_item_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='transferdivergence',
            constraint=models.CheckConstraint(condition=models.Q(('dispatched_quantity_snapshot__gt', 0), ('received_quantity_snapshot__gte', 0), ('initial_quantity__gt', 0), ('resolved_quantity__gte', 0), ('pending_quantity__gte', 0)), name='inventory_transfer_divergence_values_valid'),
        ),
        migrations.AddConstraint(
            model_name='transferdivergenceresolution',
            constraint=models.UniqueConstraint(fields=('divergence', 'idempotency_key'), name='inventory_transfer_resolution_idempotency_unique'),
        ),
        migrations.AddConstraint(
            model_name='transferdivergenceresolution',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='inventory_transfer_resolution_quantity_positive'),
        ),
    ]
