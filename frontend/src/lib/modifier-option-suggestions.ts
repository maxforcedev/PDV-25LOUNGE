export interface ModifierOptionSuggestionForm {
  name: string;
  additional_price: string;
  stock_product: string;
}

export interface ModifierProductSuggestion {
  id: number;
  name: string;
  sale_price: string;
  effective_sale_price?: string;
}

export function applyModifierProductSuggestion<T extends ModifierOptionSuggestionForm>(
  form: T,
  product: ModifierProductSuggestion,
  touched: { name: boolean; additionalPrice: boolean },
): T {
  return {
    ...form,
    stock_product: String(product.id),
    name: touched.name ? form.name : product.name,
    additional_price: touched.additionalPrice
      ? form.additional_price
      : product.effective_sale_price || product.sale_price,
  } as T;
}
