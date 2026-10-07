from apps.inventory.permissions import InventoryFunctionalPermission
class ProductionFunctionalPermission(InventoryFunctionalPermission):
    required_feature = 'production'
