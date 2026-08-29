"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  BadgeDollarSign,
  CheckCircle2,
  Percent,
  Heart,
  Minus,
  Plus,
  ReceiptText,
  Search,
  ShoppingBasket,
  Trash2,
} from "lucide-react";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
} from "@/components/ui";
import { canonicalMoney } from "@/lib/cash";
import { formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  centsToDecimal,
  moneyToCents,
  provisionalItemTotal,
  quantityToThousandths,
  sumMoney,
} from "@/lib/sales";
import { useAuth } from "@/providers/auth-provider";
import { ModifierPicker } from "@/components/modifier-picker";
import { CustomerQuickPicker } from "@/components/customer-quick-picker";
import type {
  CheckoutCashSession,
  CheckoutOptions,
  CheckoutPaymentMethod,
  ModifierSelection,
  Paginated,
  Product,
  Sale,
  SaleBeneficiary,
  SaleCategory,
  SaleOperation,
  SalePreview,
  SaleUserOption,
  Customer,
} from "@/types";

type CartItem = Product & {
  cartLineId: number;
  quantity: string;
  item_discount: string;
  modifiers: ModifierSelection[];
  modifierUnitTotal: string;
};
type PaymentRow = {
  key: number;
  payment_method: string;
  amount: string;
  received_amount: string;
};
type PricingPayload = {
  operation_type: SaleOperation;
  items: Array<{
    product: number;
    quantity: string;
    discount: string;
    modifiers: ModifierSelection[];
  }>;
  beneficiary_user?: number;
  charged_amount?: string;
  discount?: string;
  service_fee_waived?: boolean;
};
let paymentKey = 1;
let cartLineKey = 1;
const canonicalDecimal = /^\d+\.\d{2}$/;
const userTypeLabels: Record<string, string> = {
  employee: "Funcionário",
  promoter: "Promoter",
  dj: "DJ",
  artist: "Artista",
  other: "Outro",
};

function newIdempotencyKey() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const value = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}

function errorText(caught: unknown, fallback: string) {
  if (!(caught instanceof ApiError)) return fallback;
  return Object.values(caught.fields).flat().join(" ") || caught.message;
}

function validPreviewContract(value: unknown): value is SalePreview {
  if (!value || typeof value !== "object") return false;
  const preview = value as Record<string, unknown>;
  const money = (item: unknown) =>
    typeof item === "string" && canonicalDecimal.test(item);
  if (
    ![
      preview.subtotal,
      preview.promotion_discount_total,
      preview.item_discount_total,
      preview.discount,
      preview.service_fee_rate,
      preview.service_fee_amount,
      preview.reference_total,
      preview.total,
    ].every(money) ||
    (preview.commission_rate !== undefined &&
      !money(preview.commission_rate)) ||
    (preview.commission_amount !== undefined &&
      !money(preview.commission_amount))
  )
    return false;
  if (preview.charged_amount !== null && !money(preview.charged_amount))
    return false;
  if (!Array.isArray(preview.items)) return false;
  return preview.items.every((item) => {
    if (!item || typeof item !== "object") return false;
    const row = item as Record<string, unknown>;
    return (
      money(row.unit_price) &&
      money(row.subtotal) &&
      money(row.promotion_benefit) &&
      money(row.manual_discount) &&
      money(row.net_subtotal) &&
      (row.promotion_discount_value === null ||
        money(row.promotion_discount_value)) &&
      (row.unit_cost === undefined ||
        row.unit_cost === null ||
        money(row.unit_cost))
    );
  });
}

export function SalesPdv() {
  const { user, currentCompany, currentBranch, hasFeature, hasPermission } =
    useAuth();
  const cashEnabled = hasFeature("cash_register");
  const canSale =
    hasPermission(permissions.createSale) &&
    hasFeature("counter") &&
    cashEnabled;
  const canConsumption =
    hasPermission(permissions.createConsumption) && hasFeature("consumption");
  const [operation, setOperation] = useState<SaleOperation>(
    canSale ? "sale" : "consumption",
  );
  const consumption = operation === "consumption";
  const canDiscount = !consumption && hasPermission(permissions.applyDiscount);
  const canItemDiscount =
    !consumption && hasPermission(permissions.applyItemDiscount);
  const canWaiveServiceFee =
    !consumption && hasPermission(permissions.waiveServiceFee);
  const serviceFeeEnabled =
    !consumption &&
    Boolean(
      (
        currentBranch?.features as
          Record<string, { enabled: boolean }> | undefined
      )?.service_fee?.enabled,
    );
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const requestRef = useRef(0);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [nextCatalog, setNextCatalog] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<SaleCategory[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [modifierProduct, setModifierProduct] = useState<Product | null>(null);
  const [methods, setMethods] = useState<CheckoutPaymentMethod[]>([]);
  const [sessions, setSessions] = useState<CheckoutCashSession[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<SaleBeneficiary[]>([]);
  const [sellers, setSellers] = useState<SaleUserOption[]>([]);
  const [authorizers, setAuthorizers] = useState<SaleUserOption[]>([]);
  const [itemAuthorizers, setItemAuthorizers] = useState<SaleUserOption[]>([]);
  const [beneficiariesLoading, setBeneficiariesLoading] = useState(false);
  const [consumptionModal, setConsumptionModal] = useState(false);
  const [consumptionError, setConsumptionError] = useState("");
  const [beneficiary, setBeneficiary] = useState("");
  const [seller, setSeller] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [authorizer, setAuthorizer] = useState("");
  const [authorizationPassword, setAuthorizationPassword] = useState("");
  const [itemAuthorizer, setItemAuthorizer] = useState("");
  const [itemAuthorizationPassword, setItemAuthorizationPassword] =
    useState("");
  const [serviceFeeWaived, setServiceFeeWaived] = useState(false);
  const [serviceFeeAuthorizer, setServiceFeeAuthorizer] = useState("");
  const [serviceFeePassword, setServiceFeePassword] = useState("");
  const [discount, setDiscount] = useState("0.00");
  const [discountOpen, setDiscountOpen] = useState(false);
  const [feeOpen, setFeeOpen] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);
  const [charged, setCharged] = useState("0.00");
  const [cashSession, setCashSession] = useState("");
  const [splitPeople, setSplitPeople] = useState("1");
  const [payments, setPayments] = useState<PaymentRow[]>([
    { key: paymentKey++, payment_method: "", amount: "", received_amount: "" },
  ]);
  const [preview, setPreview] = useState<SalePreview | null>(null);
  const [previewSignature, setPreviewSignature] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [loadingError, setLoadingError] = useState("");
  const [resourceErrors, setResourceErrors] = useState<Record<string, string>>(
    {},
  );
  const [previewError, setPreviewError] = useState("");
  const [finalizing, setFinalizing] = useState(false);
  const [sale, setSale] = useState<Sale | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  function catalogPath() {
    const params = new URLSearchParams({ operation_type: operation });
    if (search.trim()) params.set("search", search.trim());
    if (category === "favorites") params.set("favorites", "true");
    else if (category) params.set("category", category);
    return `sales/catalog/?${params}`;
  }

  async function loadCatalog(
    path?: string,
    append = false,
    context = contextRef.current,
  ) {
    if (!currentBranch) {
      setCatalogLoading(false);
      return;
    }
    setCatalogLoading(true);
    setLoadingError("");
    try {
      const response = await http.get<Paginated<Product>>(
        path || catalogPath(),
      );
      if (contextRef.current === context) {
        setCatalog((current) =>
          append
            ? [
                ...current,
                ...response.results.filter(
                  (item) => !current.some((old) => old.id === item.id),
                ),
              ]
            : response.results,
        );
        setNextCatalog(response.next);
      }
    } catch (caught) {
      if (contextRef.current === context)
        setLoadingError(
          errorText(caught, "Não foi possível carregar o catálogo."),
        );
    } finally {
      if (contextRef.current === context) setCatalogLoading(false);
    }
  }

  useEffect(() => {
    const context = contextRef.current;
    const initialOperation: SaleOperation = canSale ? "sale" : "consumption";
    setOperation(initialOperation);
    requestRef.current += 1;
    setCatalog([]);
    setCategories([]);
    setMethods([]);
    setSessions([]);
    setBeneficiaries([]);
    setSellers([]);
    setAuthorizers([]);
    setItemAuthorizers([]);
    setCart([]);
    setPreview(null);
    setPreviewSignature(null);
    setPreviewError("");
    setLoadingError("");
    setResourceErrors({});
    setSearch("");
    setCategory("");
    setSale(null);
    setBeneficiary("");
    setSeller("");
    setCustomer(null);
    setAuthorizer("");
    setAuthorizationPassword("");
    setItemAuthorizer("");
    setItemAuthorizationPassword("");
    setServiceFeeWaived(false);
    setServiceFeeAuthorizer("");
    setServiceFeePassword("");
    setDiscount("0.00");
    setCharged("0.00");
    setCashSession("");
    setSplitPeople("1");
    setPayments([
      {
        key: paymentKey++,
        payment_method: "",
        amount: "",
        received_amount: "",
      },
    ]);
    idempotencyKeyRef.current = null;
    if (!currentBranch) {
      setCatalogLoading(false);
      return;
    }
    void loadCatalog(
      `sales/catalog/?operation_type=${initialOperation}`,
      false,
      context,
    );
    if (cashEnabled) {
      http
        .get<CheckoutOptions>(
          `sales/checkout-options/?operation_type=${initialOperation}`,
        )
        .then((options) => {
          if (contextRef.current !== context) return;
          const activeMethods = options.payment_methods.filter(
            (method) => method.status === "active",
          );
          setMethods(activeMethods);
          setSessions(options.cash_sessions);
          setPayments([
            {
              key: paymentKey++,
              payment_method: activeMethods[0]
                ? String(activeMethods[0].id)
                : "",
              amount: "",
              received_amount: "",
            },
          ]);
          if (options.cash_sessions.length)
            setCashSession(String(options.cash_sessions[0].id));
        })
        .catch((caught) => {
          if (contextRef.current === context)
            setResourceErrors((current) => ({
              ...current,
              options: errorText(
                caught,
                "Não foi possível carregar caixa e formas de pagamento.",
              ),
            }));
        });
    }
    http
      .get<SaleCategory[]>(
        `sales/categories/?operation_type=${initialOperation}`,
      )
      .then((items) => {
        if (contextRef.current === context) setCategories(items);
      })
      .catch((caught) => {
        if (contextRef.current === context)
          setResourceErrors((current) => ({
            ...current,
            categories: errorText(
              caught,
              "Não foi possível carregar as categorias.",
            ),
          }));
      });
    if (initialOperation === "sale") {
      Promise.all([
        http.getAll<SaleUserOption>("sales/sellers/"),
        http.getAll<SaleUserOption>("sales/discount-authorizers/"),
        http.getAll<SaleUserOption>("sales/item-discount-authorizers/"),
      ])
        .then(([sellerOptions, authorizerOptions, itemAuthorizerOptions]) => {
          if (contextRef.current !== context) return;
          setSellers(sellerOptions);
          setAuthorizers(authorizerOptions);
          setItemAuthorizers(itemAuthorizerOptions);
          const ownOption = sellerOptions.find((item) => item.id === user?.id);
          setSeller(ownOption ? String(ownOption.id) : "");
        })
        .catch((caught) => {
          if (contextRef.current === context)
            setResourceErrors((current) => ({
              ...current,
              users: errorText(
                caught,
                "Não foi possível carregar atendentes e autorizadores.",
              ),
            }));
        });
    }
  }, [currentCompany?.id, currentBranch?.id, canSale, cashEnabled, user?.id]);

  const rawItems = cart.map((item) => ({
    product: item.id,
    quantity: item.quantity.replace(",", "."),
    discount: consumption ? "0.00" : item.item_discount.replace(",", "."),
    modifiers: item.modifiers || [],
  }));
  const pricingPayload: PricingPayload = {
    operation_type: operation,
    items: rawItems,
    ...(consumption
      ? {
          beneficiary_user: Number(beneficiary),
          charged_amount: charged.replace(",", "."),
        }
      : {
          discount: discount.replace(",", "."),
          service_fee_waived: serviceFeeWaived,
        }),
  };
  const pricingSignature = JSON.stringify(pricingPayload);
  function invalidatePreview() {
    requestRef.current += 1;
    setPreview(null);
    setPreviewSignature(null);
    setCalculating(false);
    setPreviewError("");
    idempotencyKeyRef.current = null;
  }
  useEffect(() => {
    invalidatePreview();
    if (!cart.length || (consumption && !beneficiary)) return;
    if (
      cart.some(
        (item) =>
          quantityToThousandths(item.quantity) === null ||
          quantityToThousandths(item.quantity) === BigInt(0),
      )
    ) {
      setPreviewError("Revise as quantidades dos itens.");
      return;
    }
    const timer = window.setTimeout(
      () => void calculate(pricingPayload, pricingSignature),
      450,
    );
    return () => window.clearTimeout(timer);
  }, [pricingSignature]);

  async function calculate(
    payload = pricingPayload,
    signature = pricingSignature,
  ) {
    const request = ++requestRef.current;
    const context = contextRef.current;
    setPreview(null);
    setPreviewSignature(null);
    setCalculating(true);
    setPreviewError("");
    try {
      const result: unknown = await http.post("sales/calculate/", payload);
      if (requestRef.current === request && contextRef.current === context) {
        if (!validPreviewContract(result)) {
          setPreviewError("Contrato monetário inválido recebido da API");
          return;
        }
        setPreview(result);
        setPreviewSignature(signature);
        setPayments((rows) =>
          rows.map((row, index) =>
            index === 0 && rows.length === 1
              ? { ...row, amount: result.total }
              : row,
          ),
        );
      }
    } catch (caught) {
      if (requestRef.current === request && contextRef.current === context)
        setPreviewError(
          errorText(caught, "Não foi possível revisar os valores."),
        );
    } finally {
      if (requestRef.current === request && contextRef.current === context)
        setCalculating(false);
    }
  }

  function add(product: Product, modifiers: ModifierSelection[] = []) {
    invalidatePreview();
    setSale(null);
    setCart((current) =>
      !modifiers.length &&
      current.some((item) => item.id === product.id && !item.modifiers.length)
        ? current.map((item) => {
            if (item.id !== product.id || item.modifiers.length) return item;
            const next =
              (quantityToThousandths(item.quantity) || BigInt(0)) +
              BigInt(1000);
            return {
              ...item,
              quantity:
                item.unit === "un"
                  ? String(next / BigInt(1000))
                  : `${next / BigInt(1000)}.${String(next % BigInt(1000)).padStart(3, "0")}`,
            };
          })
        : [
            ...current,
            {
              ...product,
              cartLineId: cartLineKey++,
              quantity: product.unit === "un" ? "1" : "1.000",
              item_discount: "0.00",
              modifiers,
              modifierUnitTotal: modifiers
                .reduce((total, selection) => {
                  const option = (product.modifier_groups || [])
                    .flatMap((group) => group.options || [])
                    .find((item) => item.id === selection.option);
                  return (
                    total +
                    Number(option?.additional_price || 0) *
                      Number(selection.quantity)
                  );
                }, 0)
                .toFixed(2),
            },
          ],
    );
  }
  function requestAdd(product: Product) {
    if (
      (product.modifier_groups || []).some((group) => group.status === "active")
    )
      setModifierProduct(product);
    else add(product);
  }
  function quantity(cartLineId: number, value: string) {
    invalidatePreview();
    setCart((current) =>
      current.map((item) =>
        item.cartLineId === cartLineId ? { ...item, quantity: value } : item,
      ),
    );
  }
  function itemDiscount(cartLineId: number, value: string) {
    invalidatePreview();
    setCart((current) =>
      current.map((item) =>
        item.cartLineId === cartLineId
          ? { ...item, item_discount: value }
          : item,
      ),
    );
  }
  function remove(cartLineId: number) {
    invalidatePreview();
    setCart((current) =>
      current.filter((item) => item.cartLineId !== cartLineId),
    );
  }
  function updatePayment(
    key: number,
    field: keyof Omit<PaymentRow, "key">,
    value: string,
  ) {
    setPayments((current) =>
      current.map((row) =>
        row.key === key
          ? {
              ...row,
              [field]: value,
              ...(field === "payment_method" &&
              methods.find((item) => String(item.id) === value)?.code !== "cash"
                ? { received_amount: "" }
                : {}),
            }
          : row,
      ),
    );
  }

  function splitPaymentByPeople() {
    const people = Math.max(1, Number(splitPeople) || 1);
    const total = moneyToCents(preview?.total);
    if (total === null) return;
    const base = total / BigInt(people);
    const remainder = total % BigInt(people);
    const method = methods[0] ? String(methods[0].id) : "";
    setPayments(
      Array.from({ length: people }, (_, index) => {
        const amount = centsToDecimal(
          base + (BigInt(index) < remainder ? BigInt(1) : BigInt(0)),
        );
        return {
          key: paymentKey++,
          payment_method: method,
          amount,
          received_amount: "",
        };
      }),
    );
  }

  function openConsumption() {
    if (!canConsumption) return;
    setConsumptionModal(true);
    setConsumptionError("");
    if (beneficiaries.length || beneficiariesLoading) return;
    setBeneficiariesLoading(true);
    http
      .getAll<SaleBeneficiary>("sales/beneficiaries/")
      .then(setBeneficiaries)
      .catch((caught) =>
        setConsumptionError(
          errorText(caught, "Não foi possível carregar os beneficiários."),
        ),
      )
      .finally(() => setBeneficiariesLoading(false));
  }
  function applyConsumption() {
    const canonical = cashEnabled ? canonicalMoney(charged) : "0.00";
    if (!beneficiary || canonical === null) {
      setConsumptionError(
        "Selecione o beneficiário e informe um valor cobrado válido, inclusive zero.",
      );
      return;
    }
    setCharged(canonical);
    setOperation("consumption");
    setDiscount("0.00");
    setCart((current) =>
      current.map((item) => ({ ...item, item_discount: "0.00" })),
    );
    setConsumptionModal(false);
    invalidatePreview();
  }
  function backToSale() {
    setOperation("sale");
    setBeneficiary("");
    setCharged("0.00");
    invalidatePreview();
  }

  const provisionalCents = cart.reduce<bigint | null>((total, item) => {
    if (total === null) return null;
    const itemTotal = provisionalItemTotal(
      (Number(item.sale_price) + Number(item.modifierUnitTotal)).toFixed(2),
      item.quantity,
    );
    return itemTotal === null ? null : total + itemTotal;
  }, BigInt(0));
  const provisional =
    provisionalCents === null ? null : centsToDecimal(provisionalCents);
  const totalCents = preview ? moneyToCents(preview.total) : null;
  const nonCashAmounts = payments
    .filter(
      (row) =>
        methods.find((item) => String(item.id) === row.payment_method)?.code !==
        "cash",
    )
    .map((row) => row.amount);
  const nonCashTotal = sumMoney(nonCashAmounts);
  const explicitCashTotal = sumMoney(
    payments
      .filter(
        (row) =>
          methods.find((item) => String(item.id) === row.payment_method)
            ?.code === "cash" && row.amount,
      )
      .map((row) => row.amount),
  );
  const hasAutomaticCashRow = payments.some(
    (row) =>
      methods.find((item) => String(item.id) === row.payment_method)?.code ===
        "cash" && !row.amount,
  );
  const cashRemainingCents =
    totalCents !== null
      ? totalCents -
        (nonCashTotal || BigInt(0)) -
        (explicitCashTotal || BigInt(0))
      : null;
  const effectivePaymentCents =
    (nonCashTotal || BigInt(0)) +
    (explicitCashTotal || BigInt(0)) +
    (hasAutomaticCashRow &&
    cashRemainingCents !== null &&
    cashRemainingCents > BigInt(0)
      ? cashRemainingCents
      : BigInt(0));
  const free = consumption && totalCents === BigInt(0);
  const paymentValid =
    !!cashSession &&
    (free ||
      (!!preview &&
        payments.length > 0 &&
        effectivePaymentCents === totalCents &&
        payments.every((row) => {
          const method = methods.find(
            (item) => String(item.id) === row.payment_method,
          );
          if (!method) return false;
          if (method.code === "cash") {
            const received = moneyToCents(row.received_amount);
            const amount = row.amount
              ? moneyToCents(row.amount)
              : cashRemainingCents;
            return (
              received !== null &&
              amount !== null &&
              amount > BigInt(0) &&
              received >= amount
            );
          }
          const amount = moneyToCents(row.amount);
          return amount !== null && amount > 0 && !row.received_amount;
        })));
  const discountAuthorizationRequired = Boolean(
    !consumption && !canDiscount && preview && preview.discount !== "0.00",
  );
  const itemDiscountAuthorizationRequired = Boolean(
    !consumption &&
    !canItemDiscount &&
    preview &&
    preview.item_discount_total !== "0.00",
  );
  const serviceFeeAuthorizationRequired = Boolean(
    !consumption && serviceFeeWaived && !canWaiveServiceFee,
  );
  const saleContextValid = consumption
    ? true
    : Boolean(
        seller &&
        (!discountAuthorizationRequired ||
          (authorizer && authorizationPassword)) &&
        (!itemDiscountAuthorizationRequired ||
          (itemAuthorizer && itemAuthorizationPassword)) &&
        (!serviceFeeAuthorizationRequired ||
          (serviceFeeAuthorizer && serviceFeePassword)),
      );

  async function finalize() {
    if (
      !preview ||
      previewSignature !== pricingSignature ||
      !paymentValid ||
      !saleContextValid ||
      finalizing
    )
      return;
    setFinalizing(true);
    setPreviewError("");
    try {
      if (!idempotencyKeyRef.current) {
        idempotencyKeyRef.current = newIdempotencyKey();
      }
      const result = await http.post<Sale>("sales/finalize/", {
        idempotency_key: idempotencyKeyRef.current,
        operation_type: operation,
        items: rawItems,
        ...(consumption
          ? {
              beneficiary_user: Number(beneficiary),
              charged_amount: canonicalMoney(charged),
              discount: "0.00",
            }
          : {
              seller_user: Number(seller),
              ...(customer ? { customer: customer.id } : {}),
              discount: canonicalMoney(discount),
              service_fee_waived: serviceFeeWaived,
              ...(discountAuthorizationRequired
                ? {
                    discount_authorization: {
                      user: Number(authorizer),
                      method: "password",
                      credential: authorizationPassword,
                    },
                  }
                : {}),
              ...(itemDiscountAuthorizationRequired
                ? {
                    item_discount_authorization: {
                      user: Number(itemAuthorizer),
                      method: "password",
                      credential: itemAuthorizationPassword,
                    },
                  }
                : {}),
              ...(serviceFeeAuthorizationRequired
                ? {
                    service_fee_authorization: {
                      user: Number(serviceFeeAuthorizer),
                      method: "password",
                      credential: serviceFeePassword,
                    },
                  }
                : {}),
            }),
        cash_session: Number(cashSession),
        payments: free
          ? []
          : payments.map((row) => {
              const isCash =
                methods.find((item) => String(item.id) === row.payment_method)
                  ?.code === "cash";
              return {
                payment_method: Number(row.payment_method),
                ...(isCash
                  ? {
                      amount: row.amount
                        ? canonicalMoney(row.amount)
                        : "remaining",
                      received_amount: canonicalMoney(row.received_amount),
                    }
                  : { amount: canonicalMoney(row.amount) }),
              };
            }),
      });
      requestRef.current += 1;
      setSale(result);
      setCart([]);
      setPreview(null);
      setPreviewSignature(null);
      setDiscount("0.00");
      setCharged("0.00");
      setBeneficiary("");
      setCustomer(null);
      setAuthorizationPassword("");
      setAuthorizer("");
      setItemAuthorizationPassword("");
      setItemAuthorizer("");
      idempotencyKeyRef.current = null;
      setPayments([
        {
          key: paymentKey++,
          payment_method: methods[0] ? String(methods[0].id) : "",
          amount: "",
          received_amount: "",
        },
      ]);
    } catch (caught) {
      setPreviewError(
        errorText(
          caught,
          "Não foi possível finalizar. A operação não foi concluída.",
        ),
      );
    } finally {
      setFinalizing(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-4.5rem)] bg-operational-canvas p-3 sm:p-5">
      <div className="mx-auto max-w-[1600px]">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-operational-surface px-5 py-4 text-operational-fg">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[.2em] text-operational-info">
              {consumption ? "Consumo interno" : "Frente de caixa"}
            </p>
            <h1 className="mt-1 text-xl font-bold">
              PDV {consumption ? "· Consumação" : ""}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 p-1 text-xs">
              {sessions.length ? (
                <select
                  aria-label="Sessão de caixa ativa"
                  value={cashSession || String(sessions[0].id)}
                  onChange={(event) => setCashSession(event.target.value)}
                  className="rounded bg-success/20 px-2 py-1 font-bold text-success outline-none"
                >
                  {sessions.map((session) => (
                    <option key={session.id} value={session.id} className="text-slate-900">
                      {session.register_name}
                    </option>
                  ))}
                </select>
              ) : (
                <Link
                  href="/caixas/abrir?return=/pdv"
                  className="rounded bg-danger/20 px-2 py-1 font-bold text-danger"
                >
                  <BadgeDollarSign className="mr-1 inline size-3" />
                  Caixa fechado
                </Link>
              )}
              {!consumption && (
                <button
                  type="button"
                  className="rounded px-2 py-1 hover:bg-white/10"
                  onClick={() => setDiscountOpen(true)}
                >
                  <Percent className="mr-1 inline size-3" />
                  Desconto
                </button>
              )}
              {serviceFeeEnabled && (
                <button
                  type="button"
                  className="rounded px-2 py-1 hover:bg-white/10"
                  onClick={() => setFeeOpen(true)}
                >
                  Taxa
                </button>
              )}
              {canConsumption && (
                <button
                  type="button"
                  className="rounded px-2 py-1 hover:bg-white/10"
                  onClick={openConsumption}
                >
                  Consumação
                </button>
              )}
              {!consumption && (
                <button
                  type="button"
                  className="rounded px-2 py-1 hover:bg-white/10"
                  onClick={() => setSplitOpen(true)}
                >
                  Dividir
                </button>
              )}
            </div>
            <div className="rounded-lg bg-white/10 px-4 py-2 text-right">
              <span className="block text-[10px] uppercase tracking-wider text-operational-muted">
                Filial em operação
              </span>
              <strong className="text-sm">
                {currentBranch?.name || "Sem filial ativa"}
              </strong>
            </div>
          </div>
        </div>
        {[loadingError, ...Object.values(resourceErrors)]
          .filter(Boolean)
          .map((message, index) => (
            <div className="mb-4" key={`${message}-${index}`}>
              <Alert message={message} />
            </div>
          ))}
        {sale && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-success/30 bg-success-surface px-5 py-4 text-success-strong">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="size-6" />
              <div>
                <strong className="block">
                  {sale.operation_type === "consumption"
                    ? "Consumação"
                    : "Venda"}{" "}
                  {sale.sale_number} finalizada
                </strong>
                <span className="text-xs text-success-strong">
                  Total {formatBRL(sale.total)}
                </span>
              </div>
            </div>
            <Link
              className="btn btn-secondary"
              href={`/${sale.operation_type === "consumption" ? "consumacoes" : "vendas"}/${sale.id}`}
            >
              Abrir comprovante
            </Link>
          </div>
        )}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(390px,.75fr)]">
          <section className="overflow-hidden rounded-xl bg-canvas">
            <div className="border-b border-subtle bg-surface p-4">
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  void loadCatalog();
                }}
              >
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 size-4 text-slate-400" />
                  <Input
                    className="pl-9"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Nome, código interno ou código de barras"
                  />
                </div>
                <Button>Buscar</Button>
              </form>
              <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
                <button
                  className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${!category ? "bg-primary text-white" : "bg-surface-muted text-fg"}`}
                  onClick={() => {
                    setCategory("");
                    void loadCatalog(
                      `sales/catalog/?operation_type=${operation}`,
                    );
                  }}
                >
                  Todos
                </button>
                {catalog.some((product) => product.is_favorite) && (
                  <button
                    className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${category === "favorites" ? "bg-primary text-white" : "bg-surface-muted text-fg"}`}
                    onClick={() => {
                      setCategory("favorites");
                      void loadCatalog(
                        `sales/catalog/?operation_type=${operation}&favorites=true`,
                      );
                    }}
                  >
                    Favoritos
                  </button>
                )}
                {categories.map(({ id, name }) => (
                  <button
                    key={id}
                    className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${category === String(id) ? "bg-primary text-white" : "bg-surface-muted text-fg"}`}
                    onClick={() => {
                      setCategory(String(id));
                      void loadCatalog(
                        `sales/catalog/?operation_type=${operation}&category=${id}`,
                      );
                    }}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
            {catalogLoading && !catalog.length ? (
              <div className="flex h-80 items-center justify-center text-primary">
                <Spinner className="size-7" />
              </div>
            ) : catalog.length ? (
              <>
                <div className="grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-4">
                  {catalog.map((product) => (
                    <button
                      key={product.id}
                      onClick={() => requestAdd(product)}
                      className={`group relative min-h-36 rounded-xl border bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-primary hover:shadow-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/30 ${product.is_favorite ? "border-primary/40" : "border-subtle"}`}
                    >
                      {product.is_favorite && (
                        <Heart className="absolute right-3 top-3 size-4 fill-primary text-primary" />
                      )}
                      <span className="block pr-5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {product.category_name || "Geral"}
                      </span>
                      <strong className="mt-3 block text-sm leading-5 text-fg">
                        {product.name}
                      </strong>
                      <span className="mt-1 block text-[10px] text-slate-400">
                        {product.internal_code}
                      </span>
                      <span className="mt-4 block text-base font-bold text-primary">
                        {formatBRL(product.sale_price)}
                      </span>
                    </button>
                  ))}
                </div>
                {nextCatalog && (
                  <div className="p-4 pt-0 text-center">
                    <Button
                      variant="secondary"
                      loading={catalogLoading}
                      onClick={() => void loadCatalog(nextCatalog, true)}
                    >
                      Carregar mais produtos
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <EmptyState
                title="Nenhum produto disponível"
                description="Ajuste a busca ou a categoria do catálogo."
              />
            )}
          </section>
          <aside className="self-start overflow-hidden rounded-xl bg-surface xl:sticky xl:top-23">
            <div className="flex items-center justify-between border-b border-subtle px-5 py-4">
              <div>
                <h2 className="flex items-center gap-2 text-sm font-bold">
                  <ShoppingBasket className="size-4 text-primary" />
                  Carrinho atual
                </h2>
                <p className="mt-1 text-[10px] text-slate-400">
                  {cart.length} {cart.length === 1 ? "item" : "itens"}
                </p>
              </div>
              <strong className="text-lg">{formatBRL(provisional)}</strong>
            </div>
            {!cart.length ? (
              <EmptyState
                title="Carrinho vazio"
                description="Toque em um produto do catálogo para adicionar."
              />
            ) : (
              <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
                {cart.map((item) => (
                  <div key={item.cartLineId} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <strong className="text-xs">{item.name}</strong>
                        <p className="text-[10px] text-slate-400">
                          {formatBRL(
                            (
                              Number(item.sale_price) +
                              Number(item.modifierUnitTotal)
                            ).toFixed(2),
                          )}{" "}
                          / {item.unit.toUpperCase()}
                        </p>
                        {item.modifiers.length > 0 && (
                          <p className="mt-1 text-[10px] text-muted">
                            {item.modifiers
                              .map((selection) => {
                                const option = (item.modifier_groups || [])
                                  .flatMap((group) => group.options || [])
                                  .find(
                                    (value) => value.id === selection.option,
                                  );
                                return option
                                  ? `${option.name}${selection.quantity !== "1" ? ` × ${selection.quantity}` : ""}`
                                  : "";
                              })
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        )}
                      </div>
                      <button
                        className="icon-button size-7"
                        onClick={() => remove(item.cartLineId)}
                        aria-label={`Remover ${item.name}`}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        className="icon-button size-8 border border-subtle"
                        onClick={() => {
                          const q =
                            quantityToThousandths(item.quantity) || BigInt(0);
                          const step =
                            item.unit === "un" ? BigInt(1000) : BigInt(1);
                          if (q > step)
                            quantity(
                              item.cartLineId,
                              item.unit === "un"
                                ? String((q - step) / BigInt(1000))
                                : `${(q - step) / BigInt(1000)}.${String((q - step) % BigInt(1000)).padStart(3, "0")}`,
                            );
                        }}
                      >
                        <Minus className="size-3" />
                      </button>
                      <Input
                        id="pdv-discount"
                        className="h-8 w-24 text-center"
                        inputMode="decimal"
                        value={item.quantity}
                        onChange={(event) =>
                          quantity(item.cartLineId, event.target.value)
                        }
                        aria-label={`Quantidade de ${item.name}`}
                      />
                      <button
                        className="icon-button size-8 border border-subtle"
                        onClick={() => {
                          const q =
                            quantityToThousandths(item.quantity) || BigInt(0);
                          const step =
                            item.unit === "un" ? BigInt(1000) : BigInt(1);
                          const next = q + step;
                          quantity(
                            item.cartLineId,
                            item.unit === "un"
                              ? String(next / BigInt(1000))
                              : `${next / BigInt(1000)}.${String(next % BigInt(1000)).padStart(3, "0")}`,
                          );
                        }}
                      >
                        <Plus className="size-3" />
                      </button>
                      <span className="ml-auto text-xs font-bold">
                        {formatBRL(
                          provisionalItemTotal(
                            (
                              Number(item.sale_price) +
                              Number(item.modifierUnitTotal)
                            ).toFixed(2),
                            item.quantity,
                          ) === null
                            ? null
                            : centsToDecimal(
                                provisionalItemTotal(
                                  (
                                    Number(item.sale_price) +
                                    Number(item.modifierUnitTotal)
                                  ).toFixed(2),
                                  item.quantity,
                                )!,
                              ),
                        )}
                      </span>
                    </div>
                    {item.unit === "un" && !/^\d+$/.test(item.quantity) && (
                      <p className="field-error">
                        UN exige quantidade inteira.
                      </p>
                    )}
                    {!consumption && (
                      <div className="mt-2 flex items-center gap-2">
                        <label
                          className="text-[10px] font-semibold text-slate-500"
                          htmlFor={`item-discount-${item.cartLineId}`}
                        >
                          Desconto do item (R$)
                        </label>
                        <Input
                          id={`item-discount-${item.cartLineId}`}
                          className="ml-auto h-8 w-24 text-right"
                          inputMode="decimal"
                          value={item.item_discount}
                          onChange={(event) =>
                            itemDiscount(item.cartLineId, event.target.value)
                          }
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {!!cart.length && (
              <div className="space-y-4 border-t border-subtle p-5">
                <div className="flex flex-wrap gap-2">
                  {consumption && canSale && (
                    <Button variant="secondary" onClick={backToSale}>
                      Remover consumação / voltar para venda
                    </Button>
                  )}
                </div>
                {consumption && beneficiary && (
                  <div className="rounded-lg border border-primary/15 bg-primary/5 p-3 text-xs">
                    <strong>
                      {beneficiaries.find(
                        (item) => String(item.id) === beneficiary,
                      )?.name || "Beneficiário selecionado"}
                    </strong>
                    <span className="mt-1 block text-slate-500">
                      Consumação · cobrança {formatBRL(canonicalMoney(charged))}
                    </span>
                    <button
                      className="mt-2 font-bold text-primary"
                      onClick={openConsumption}
                    >
                      Alterar
                    </button>
                  </div>
                )}
                {!consumption && (
                  <Field label="Cliente" optional>
                    <CustomerQuickPicker
                      value={customer}
                      onChange={setCustomer}
                      disabled={finalizing}
                    />
                  </Field>
                )}
                {!consumption && (
                  <Field label="Atendente da venda">
                    <Select
                      required
                      value={seller}
                      onChange={(event) => setSeller(event.target.value)}
                    >
                      <option value="" disabled>
                        Selecione o atendente
                      </option>
                      {sellers.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </Select>
                    <span className="mt-1 block text-[10px] text-slate-400">
                      O operador continua registrado separadamente.
                    </span>
                  </Field>
                )}
                {!consumption && moneyToCents(discount) !== BigInt(0) && (
                  <p className="text-xs font-semibold text-primary">
                    Desconto aplicado · {formatBRL(canonicalMoney(discount))}
                  </p>
                )}
                {discountAuthorizationRequired && (
                  <div className="space-y-3 rounded-lg border border-warning/30 bg-warning-surface p-4">
                    <strong className="block text-xs text-warning-strong">
                      Autorização de desconto
                    </strong>
                    <Field label="Autorizador">
                      <Select
                        required
                        value={authorizer}
                        onChange={(event) => setAuthorizer(event.target.value)}
                      >
                        <option value="" disabled>
                          Selecione quem autoriza
                        </option>
                        {authorizers.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Senha do autorizador">
                      <Input
                        required
                        type="password"
                        autoComplete="current-password"
                        value={authorizationPassword}
                        onChange={(event) =>
                          setAuthorizationPassword(event.target.value)
                        }
                      />
                    </Field>
                  </div>
                )}
                {itemDiscountAuthorizationRequired && (
                  <div className="space-y-3 rounded-lg border border-warning/30 bg-warning-surface p-4">
                    <strong className="block text-xs text-warning-strong">
                      Autorização de desconto por item
                    </strong>
                    <Field label="Autorizador">
                      <Select
                        required
                        value={itemAuthorizer}
                        onChange={(event) =>
                          setItemAuthorizer(event.target.value)
                        }
                      >
                        <option value="" disabled>
                          Selecione quem autoriza
                        </option>
                        {itemAuthorizers.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Senha do autorizador">
                      <Input
                        required
                        type="password"
                        autoComplete="current-password"
                        value={itemAuthorizationPassword}
                        onChange={(event) =>
                          setItemAuthorizationPassword(event.target.value)
                        }
                      />
                    </Field>
                  </div>
                )}
                {false && !consumption && (
                  <label className="flex items-center gap-3 rounded-lg border border-subtle p-4 text-xs font-semibold">
                    <input
                      id="pdv-fee"
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={serviceFeeWaived}
                      onChange={(event) => {
                        invalidatePreview();
                        setServiceFeeWaived(event.target.checked);
                      }}
                    />
                    <span>
                      <strong className="block">Retirar taxa de serviço</strong>
                      <small className="font-normal text-slate-400">
                        {canWaiveServiceFee
                          ? "Permitido pelo seu perfil."
                          : "Exige autorização pontual."}
                      </small>
                    </span>
                  </label>
                )}
                {serviceFeeAuthorizationRequired && (
                  <div className="space-y-3 rounded-lg border border-warning/30 bg-warning-surface p-4">
                    <strong className="block text-xs text-warning-strong">
                      Autorização para retirar taxa
                    </strong>
                    <Field label="Autorizador">
                      <Select
                        required
                        value={serviceFeeAuthorizer}
                        onChange={(event) =>
                          setServiceFeeAuthorizer(event.target.value)
                        }
                      >
                        <option value="" disabled>
                          Selecione quem autoriza
                        </option>
                        {authorizers.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Senha do autorizador">
                      <Input
                        required
                        type="password"
                        autoComplete="current-password"
                        value={serviceFeePassword}
                        onChange={(event) =>
                          setServiceFeePassword(event.target.value)
                        }
                      />
                    </Field>
                  </div>
                )}
                {previewError && <Alert message={previewError} />}
                {calculating && (
                  <div className="flex items-center gap-2 text-xs text-primary">
                    <Spinner />
                    Revisando valores na API...
                  </div>
                )}
                {preview && (
                  <div className="rounded-lg bg-operational-surface p-4 text-operational-fg">
                    <div className="flex justify-between text-xs text-operational-muted">
                      <span>
                        {consumption
                          ? "Subtotal de referência"
                          : "Subtotal bruto"}
                      </span>
                      <span>{formatBRL(preview.subtotal)}</span>
                    </div>
                    {!consumption &&
                      preview.promotion_discount_total !== "0.00" && (
                        <div className="mt-2 flex justify-between text-xs text-operational-success">
                          <span>Benefício promocional</span>
                          <span>
                            - {formatBRL(preview.promotion_discount_total)}
                          </span>
                        </div>
                      )}
                    {!consumption && (
                      <div className="mt-2 flex justify-between text-xs text-operational-muted">
                        <span>Desconto na conta</span>
                        <span>- {formatBRL(preview.discount)}</span>
                      </div>
                    )}
                    {!consumption && preview.item_discount_total !== "0.00" && (
                      <div className="mt-2 flex justify-between text-xs text-operational-warning">
                        <span>Descontos por item</span>
                        <span>- {formatBRL(preview.item_discount_total)}</span>
                      </div>
                    )}
                    {!consumption && preview.service_fee_amount !== "0.00" && (
                      <div className="mt-2 flex justify-between text-xs text-operational-info">
                        <span>
                          Taxa de serviço ({preview.service_fee_rate}%)
                        </span>
                        <span>+ {formatBRL(preview.service_fee_amount)}</span>
                      </div>
                    )}
                    {!consumption && preview.service_fee_waived && (
                      <div className="mt-2 flex justify-between text-xs text-operational-warning">
                        <span>Taxa de serviço retirada</span>
                        <span>{preview.service_fee_rate}%</span>
                      </div>
                    )}
                    {consumption && (
                      <div className="mt-2 flex justify-between text-xs text-operational-muted">
                        <span>Valor cobrado</span>
                        <span>{formatBRL(preview.charged_amount)}</span>
                      </div>
                    )}
                    {!consumption &&
                      preview.items.some((item) => item.promotion) && (
                        <div className="mt-3 space-y-1 border-t border-white/10 pt-3">
                          {preview.items
                            .filter((item) => item.promotion)
                            .map((item) => (
                              <div
                                key={item.product}
                                className="flex justify-between text-[10px] text-operational-success"
                              >
                                <span>
                                  {item.product_name} · {item.promotion_name}
                                </span>
                                <span>
                                  {formatBRL(item.subtotal)} →{" "}
                                  {formatBRL(item.net_subtotal)}
                                </span>
                              </div>
                            ))}
                        </div>
                      )}
                    <div className="mt-3 flex justify-between border-t border-white/10 pt-3">
                      <strong>Total a pagar</strong>
                      <strong className="text-xl text-operational-info">
                        {formatBRL(preview.total)}
                      </strong>
                    </div>
                  </div>
                )}
                {preview && !free && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <strong className="text-xs">Pagamentos</strong>
                      <button
                        className="text-xs font-bold text-primary"
                        onClick={() =>
                          setPayments((current) => [
                            ...current,
                            {
                              key: paymentKey++,
                              payment_method: methods[0]
                                ? String(methods[0].id)
                                : "",
                              amount: "",
                              received_amount: "",
                            },
                          ])
                        }
                      >
                        + Dividir pagamento
                      </button>
                    </div>
                    {false && (
                      <div className="rounded-lg border border-subtle p-3">
                        <div className="grid gap-2 sm:grid-cols-[150px_1fr]">
                          <Field label="Dividir por pessoas">
                            <Input
                              inputMode="numeric"
                              min={1}
                              value={splitPeople}
                              onChange={(event) =>
                                setSplitPeople(
                                  event.target.value.replace(/\D/g, "") || "1",
                                )
                              }
                            />
                          </Field>
                          <Button
                            type="button"
                            variant="secondary"
                            className="self-end"
                            onClick={splitPaymentByPeople}
                          >
                            Gerar linhas
                          </Button>
                          <div className="self-end pb-2 text-xs text-slate-500">
                            Valor por pessoa:{" "}
                            <strong className="text-slate-900">
                              {preview
                                ? formatBRL(
                                    centsToDecimal(
                                      (moneyToCents(preview?.total) ||
                                        BigInt(0)) /
                                        BigInt(
                                          Math.max(1, Number(splitPeople) || 1),
                                        ),
                                    ),
                                  )
                                : "-"}
                            </strong>
                            . Esta calculadora não altera a venda nem os
                            pagamentos.
                          </div>
                        </div>
                      </div>
                    )}
                    {payments.map((row) => {
                      const method = methods.find(
                        (item) => String(item.id) === row.payment_method,
                      );
                      const isCash = method?.code === "cash";
                      const received = moneyToCents(row.received_amount);
                      const cashAmount =
                        isCash && row.amount
                          ? moneyToCents(row.amount) || BigInt(0)
                          : isCash &&
                              cashRemainingCents !== null &&
                              cashRemainingCents > BigInt(0)
                            ? cashRemainingCents
                            : BigInt(0);
                      return (
                        <div
                          key={row.key}
                          className="rounded-lg border border-subtle p-3"
                        >
                          <div className="grid gap-2 sm:grid-cols-2">
                            <Select
                              value={row.payment_method}
                              onChange={(event) =>
                                updatePayment(
                                  row.key,
                                  "payment_method",
                                  event.target.value,
                                )
                              }
                            >
                              <option value="">Forma</option>
                              {methods.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.name}
                                </option>
                              ))}
                            </Select>
                            {isCash ? (
                              <Input
                                inputMode="decimal"
                                placeholder="Valor"
                                value={row.amount}
                                onChange={(event) =>
                                  updatePayment(
                                    row.key,
                                    "amount",
                                    event.target.value,
                                  )
                                }
                              />
                            ) : (
                              <Input
                                inputMode="decimal"
                                placeholder="Valor"
                                value={row.amount}
                                onChange={(event) =>
                                  updatePayment(
                                    row.key,
                                    "amount",
                                    event.target.value,
                                  )
                                }
                              />
                            )}
                          </div>
                          {isCash && (
                            <div className="mt-2 grid grid-cols-2 gap-2">
                              <Input
                                inputMode="decimal"
                                placeholder="Valor recebido"
                                value={row.received_amount}
                                onChange={(event) =>
                                  updatePayment(
                                    row.key,
                                    "received_amount",
                                    event.target.value,
                                  )
                                }
                              />
                              <div className="rounded-md bg-surface-muted px-3 py-2 text-xs">
                                <span className="block text-[9px] uppercase text-slate-400">
                                  Troco previsto
                                </span>
                                <strong>
                                  {formatBRL(
                                    centsToDecimal(
                                      received !== null &&
                                        received >= cashAmount
                                        ? received - cashAmount
                                        : BigInt(0),
                                    ),
                                  )}
                                </strong>
                              </div>
                            </div>
                          )}
                          {payments.length > 1 && (
                            <button
                              className="mt-2 text-[10px] font-bold text-danger"
                              onClick={() =>
                                setPayments((current) =>
                                  current.filter(
                                    (item) => item.key !== row.key,
                                  ),
                                )
                              }
                            >
                              Remover pagamento
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                {preview && free && (
                  <div className="rounded-lg border border-success/20 bg-success-surface p-3 text-xs text-success-strong">
                    Consumação sem cobrança: dispensa forma de pagamento, mas
                    exige uma sessão de Caixa aberta.
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => void calculate()}
                    loading={calculating}
                    disabled={consumption && !beneficiary}
                  >
                    Revisar
                  </Button>
                  <Button
                    className="flex-[1.5]"
                    onClick={() => void finalize()}
                    loading={finalizing}
                    disabled={
                      !preview ||
                      previewSignature !== pricingSignature ||
                      calculating ||
                      !paymentValid ||
                      !saleContextValid
                    }
                  >
                    <ReceiptText className="size-4" />
                    Finalizar
                  </Button>
                </div>
              </div>
            )}
          </aside>
        </div>
        <Modal
          open={consumptionModal}
          title="Aplicar consumação"
          description="O mesmo carrinho será recalculado como consumação."
          onClose={() => !beneficiariesLoading && setConsumptionModal(false)}
          size="md"
        >
          <div className="space-y-4 p-5 sm:p-6">
            {consumptionError && <Alert message={consumptionError} />}
            <Field label="Beneficiário">
              <Select
                autoFocus
                required
                disabled={beneficiariesLoading}
                value={beneficiary}
                onChange={(event) => setBeneficiary(event.target.value)}
              >
                <option value="">
                  {beneficiariesLoading ? "Carregando..." : "Selecione"}
                </option>
                {beneficiaries.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {userTypeLabels[item.user_type] || "Outro"}
                    {!item.can_login ? " · sem login" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Valor cobrado (R$)">
              <Input
                required
                inputMode="decimal"
                value={charged}
                onChange={(event) => setCharged(event.target.value)}
                disabled={!cashEnabled}
              />
              <span className="mt-1 block text-[10px] text-slate-400">
                {cashEnabled
                  ? "Pode ser zero; o servidor validará o limite pelo subtotal."
                  : "A Consumação requer Caixa habilitado nesta filial."}
              </span>
            </Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              variant="secondary"
              onClick={() => setConsumptionModal(false)}
            >
              Cancelar
            </Button>
            <Button onClick={applyConsumption} disabled={beneficiariesLoading}>
              Confirmar consumação
            </Button>
          </div>
        </Modal>
        <Modal
          open={discountOpen}
          title="Desconto"
          description="Aplique desconto por valor. Autorizações continuam sendo validadas no fechamento."
          onClose={() => setDiscountOpen(false)}
          size="md"
        >
          <div className="space-y-4 p-5">
            <Field label="Valor do desconto (R$)">
              <Input
                autoFocus
                inputMode="decimal"
                value={discount}
                onChange={(event) => {
                  invalidatePreview();
                  setDiscount(event.target.value);
                }}
              />
            </Field>
            {discountAuthorizationRequired && (
              <p className="text-xs text-warning-strong">
                Informe autorizador e senha na seção de autorização antes de
                finalizar.
              </p>
            )}
          </div>
          <div className="flex justify-end border-t border-subtle px-5 py-4">
            <Button onClick={() => setDiscountOpen(false)}>
              Aplicar desconto
            </Button>
          </div>
        </Modal>
        <Modal
          open={feeOpen}
          title="Taxa de serviço"
          description="A taxa configurada é aplicada automaticamente. Você pode retirá-la quando autorizado."
          onClose={() => setFeeOpen(false)}
          size="md"
        >
          <div className="space-y-4 p-5">
            <p className="text-sm">Taxa atual: {preview?.service_fee_rate || "0"}%</p>
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={serviceFeeWaived}
                onChange={(event) => {
                  invalidatePreview();
                  setServiceFeeWaived(event.target.checked);
                }}
              />
              Retirar taxa de serviço
            </label>
          </div>
          <div className="flex justify-end border-t border-subtle px-5 py-4">
            <Button onClick={() => setFeeOpen(false)}>Aplicar</Button>
          </div>
        </Modal>
        <Modal
          open={splitOpen}
          title="Dividir pagamento"
          description="Gera linhas de pagamento; a venda só muda após finalizar."
          onClose={() => setSplitOpen(false)}
          size="md"
        >
          <div className="space-y-4 p-5">
            <Field label="Pessoas">
              <Input
                inputMode="numeric"
                min={1}
                value={splitPeople}
                onChange={(event) =>
                  setSplitPeople(event.target.value.replace(/\D/g, "") || "1")
                }
              />
            </Field>
            <p className="text-sm">
              Valor por pessoa:{" "}
              {preview
                ? formatBRL(
                    centsToDecimal(
                      (moneyToCents(preview.total) || BigInt(0)) /
                        BigInt(Math.max(1, Number(splitPeople) || 1)),
                    ),
                  )
                : "-"}
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4">
            <Button variant="secondary" onClick={() => setSplitOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => {
                splitPaymentByPeople();
                setSplitOpen(false);
              }}
            >
              Gerar linhas
            </Button>
          </div>
        </Modal>
        {modifierProduct && (
          <ModifierPicker
            product={modifierProduct}
            onClose={() => setModifierProduct(null)}
            onConfirm={(selections) => {
              add(modifierProduct, selections);
              setModifierProduct(null);
            }}
          />
        )}
      </div>
    </div>
  );
}
