from collections.abc import Mapping
from uuid import UUID

from django.db import transaction

from apps.catalog.exceptions import InsufficientStock, VariantUnavailable
from apps.catalog.models import ProductVariant
from apps.core.logging import get_logger
from apps.inventory.exceptions import InvalidStockAdjustment
from apps.inventory.models import (
    DECREASING_REASONS,
    INCREASING_REASONS,
    MANUAL_REASONS,
    MovementReason,
    StockMovement,
)
from apps.users.models import User

logger = get_logger(__name__)


def _reject_non_positive_quantities(quantities: Mapping[UUID, int]) -> None:
    # A zero or negative quantity would sail past the availability check and *add*
    # stock on the decrement path, corrupting inventory silently. It means a broken
    # caller rather than a rejected customer -- the serializer validates quantity
    # before any service sees it -- so this is a ValueError, not a DomainError with
    # a public error code.
    invalid = sorted(str(variant_id) for variant_id, qty in quantities.items() if qty < 1)
    if invalid:
        raise ValueError(f"Quantities must be positive integers; got non-positive for {invalid}.")


def _variants(quantities: Mapping[UUID, int], *, lock: bool) -> dict[UUID, ProductVariant]:
    variants = (
        ProductVariant.objects
        # Not speculative: `.price` falls through to product.base_price, availability
        # reads the product and its brand, and place_order snapshots the size and
        # shade names. Without the joins those are queries per variant while this
        # transaction holds the row locks.
        .select_related("product__brand", "size", "shade")
        .filter(pk__in=quantities.keys())
        # ADR 0004: locks are always taken in ascending pk order. Two carts holding
        # the same two variants in opposite orders deadlock, and Postgres resolves
        # that by killing one transaction -- an intermittent 500 that will not
        # reproduce.
        .order_by("pk")
    )
    if lock:
        # `of` restricts the lock to product_variant. Plain select_for_update()
        # alongside select_related() would also lock the joined product rows,
        # which this operation never writes and which other checkouts need.
        variants = variants.select_for_update(of=("self",))

    found = {variant.pk: variant for variant in variants}

    missing = sorted(str(variant_id) for variant_id in quantities if variant_id not in found)
    if missing:
        raise VariantUnavailable(details={"variant_ids": missing})

    return found


def _reject_unavailable(
    quantities: Mapping[UUID, int], variants: Mapping[UUID, ProductVariant]
) -> None:
    hidden = sorted(
        str(variant_id)
        for variant_id, variant in variants.items()
        if not (variant.product.is_published and variant.product.brand.is_active)
    )
    if hidden:
        raise VariantUnavailable(details={"variant_ids": hidden})

    for variant_id, quantity in quantities.items():
        if variants[variant_id].stock_quantity < quantity:
            # `available` is deliberately absent. Checkout is AllowAny, so
            # returning the remaining count would let one POST per variant
            # enumerate the whole inventory -- the disclosure
            # catalog-browsing.md refuses to make through the browsing API.
            raise InsufficientStock(
                details={
                    "variant_id": str(variant_id),
                    "requested": quantity,
                }
            )


def _movement(
    variant: ProductVariant,
    *,
    reason: MovementReason,
    quantity_change: int,
    order_id: UUID | None = None,
    actor: User | None = None,
    note: str = "",
) -> StockMovement:
    return StockMovement(
        variant=variant,
        sku=variant.sku,
        reason=reason,
        quantity_change=quantity_change,
        balance_after=variant.stock_quantity,
        order_id=order_id,
        actor=actor,
        note=note,
    )


def check_variant_availability(*, quantities: Mapping[UUID, int]) -> dict[UUID, ProductVariant]:
    """Raises what decrement_variant_stock would, without locking or writing.

    The answer can be stale by the time the customer checks out; only the locked
    decrement decides. Returns the variants so the caller can read prices.
    """
    _reject_non_positive_quantities(quantities)
    variants = _variants(quantities, lock=False)
    _reject_unavailable(quantities, variants)
    return variants


def decrement_variant_stock(
    *, quantities: Mapping[UUID, int], order_id: UUID
) -> dict[UUID, ProductVariant]:
    """Raises VariantUnavailable for an unknown variant or one hidden from the
    storefront (unpublished product or inactive brand), and InsufficientStock when a
    variant cannot cover its requested quantity.

    Records a sale against `order_id`, which may name an order not yet inserted in
    the caller's transaction. Returns the locked variants so the caller can read
    prices without refetching.
    """
    _reject_non_positive_quantities(quantities)

    with transaction.atomic():
        locked = _variants(quantities, lock=True)
        _reject_unavailable(quantities, locked)

        movements = []
        for variant_id, quantity in quantities.items():
            variant = locked[variant_id]
            variant.stock_quantity -= quantity
            variant.save(update_fields=["stock_quantity", "updated_at"])
            movements.append(
                _movement(
                    variant,
                    reason=MovementReason.SALE,
                    quantity_change=-quantity,
                    order_id=order_id,
                )
            )
        StockMovement.objects.bulk_create(movements)

        logger.info("catalog.stock_decremented", variant_count=len(locked))
        return locked


def restore_variant_stock(
    *, quantities: Mapping[UUID, int], order_id: UUID, actor: User | None
) -> dict[UUID, ProductVariant]:
    """Raises VariantUnavailable for an unknown variant.

    Unpublishing a product must not strand the stock of a cancelled order, so
    publication state is deliberately not checked here.
    """
    _reject_non_positive_quantities(quantities)

    with transaction.atomic():
        locked = _variants(quantities, lock=True)

        movements = []
        for variant_id, quantity in quantities.items():
            variant = locked[variant_id]
            variant.stock_quantity += quantity
            variant.save(update_fields=["stock_quantity", "updated_at"])
            movements.append(
                _movement(
                    variant,
                    reason=MovementReason.CANCELLATION,
                    quantity_change=quantity,
                    order_id=order_id,
                    actor=actor,
                )
            )
        StockMovement.objects.bulk_create(movements)

        logger.info("catalog.stock_restored", variant_count=len(locked))
        return locked


def set_variant_stock(
    *, variant: ProductVariant, quantity: int, actor: User | None, note: str = ""
) -> ProductVariant:
    """Raises ValueError for a negative quantity.

    Sets an absolute count, because that is what a merchant who has just counted a
    shelf knows, and records it as a stocktake whose change is the variance.
    Returns the locked variant.
    """
    if quantity < 0:
        raise ValueError(f"Stock cannot be negative; got {quantity}.")

    with transaction.atomic():
        # The write is absolute, so the lock is not about lost updates: it makes
        # the recorded variance the difference from the value this write replaced.
        locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        previous = locked.stock_quantity

        locked.stock_quantity = quantity
        locked.save(update_fields=["stock_quantity", "updated_at"])
        _movement(
            locked,
            reason=MovementReason.STOCKTAKE,
            quantity_change=quantity - previous,
            actor=actor,
            note=note,
        ).save()

    logger.info(
        "catalog.stock_set",
        variant_id=str(locked.pk),
        sku=locked.sku,
        previous=previous,
        quantity=quantity,
    )
    return locked


def adjust_variant_stock(
    *,
    variant: ProductVariant,
    quantity_change: int,
    reason: MovementReason,
    actor: User | None,
    note: str = "",
) -> StockMovement:
    """Raises InvalidStockAdjustment for a change of zero, one whose direction
    contradicts its reason, or one that would take stock below zero.

    Relative, unlike set_variant_stock, so a sale made while staff were typing is
    not overwritten.
    """
    if reason not in MANUAL_REASONS:
        raise ValueError(f"{reason} is not a manual adjustment reason.")
    label = MovementReason(reason).label
    if quantity_change == 0:
        raise InvalidStockAdjustment("An adjustment must change the stock.")
    if reason in INCREASING_REASONS and quantity_change < 0:
        raise InvalidStockAdjustment(f"{label} adds stock, so the change must be positive.")
    if reason in DECREASING_REASONS and quantity_change > 0:
        raise InvalidStockAdjustment(f"{label} removes stock, so the change must be negative.")

    with transaction.atomic():
        locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
        if locked.stock_quantity + quantity_change < 0:
            raise InvalidStockAdjustment(
                f"Only {locked.stock_quantity} in stock; cannot remove {-quantity_change}."
            )

        locked.stock_quantity += quantity_change
        locked.save(update_fields=["stock_quantity", "updated_at"])
        movement = _movement(
            locked, reason=reason, quantity_change=quantity_change, actor=actor, note=note
        )
        movement.save()

    logger.info(
        "inventory.stock_adjusted",
        variant_id=str(locked.pk),
        reason=reason,
        quantity_change=quantity_change,
        balance_after=locked.stock_quantity,
    )
    return movement
