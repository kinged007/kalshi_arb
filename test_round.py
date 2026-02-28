def align_polymarket_amounts(size: float, price: float) -> float:
    """
    Polymarket accepts max 4 decimals for the taker amount (size).
    The maker amount (size * price) supports max 2 decimals.
    This function adjusts the size down so that (size * price) has exactly 2 decimals.
    """
    # Truncate size to 4 decimals
    size = int(size * 10000) / 10000.0
    
    # Calculate Maker amount
    maker_amount = size * price
    maker_amount_rounded = int(maker_amount * 100) / 100.0
    
    if abs(maker_amount - maker_amount_rounded) > 1e-8:
        # Size needs adjustment to make maker amount exact
        new_size = maker_amount_rounded / price
        # Truncate new size to 4 decimals
        new_size = int(new_size * 10000) / 10000.0
        return new_size
    return size

print(align_polymarket_amounts(4.32, 0.89))
print(4.32 * 0.89)
print(int(4.32 * 0.89 * 100) / 100.0 / 0.89)
