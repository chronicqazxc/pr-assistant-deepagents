def print_context_usage(result_msg) -> None:
    """Print cumulative token usage from a ResultMessage."""
    usage = getattr(result_msg, 'usage', None)
    if not usage:
        return

    input_tokens = usage.get('input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    cache_read = usage.get('cache_read_input_tokens', 0)
    cache_create = usage.get('cache_creation_input_tokens', 0)
    total_input = input_tokens + cache_read + cache_create
    cache_hit_pct = (cache_read / total_input * 100) if total_input > 0 else 0

    num_turns = getattr(result_msg, 'num_turns', None)
    cost = getattr(result_msg, 'total_cost_usd', None)

    turns_str = f"{num_turns} turns" if num_turns is not None else ""
    cost_str = f"${cost:.4f}" if cost is not None else ""
    summary = " | ".join(filter(None, [turns_str, cost_str]))

    print(f"\n📊 Usage ({summary}): Cache hit {cache_hit_pct:.1f}%")
    print(f"   Cache read: {cache_read:,} | Cache created: {cache_create:,} | Input: {input_tokens:,} | Output: {output_tokens:,}")


def smart_truncate(text: str, max_size: int = 5000) -> str:
    """Truncate long text to prevent terminal/CI log buffer overflow.

    Shows the beginning of the text and appends a truncation notice.
    Full content is still preserved in the returned response dict — only display is affected.

    Args:
        text: Text to truncate
        max_size: Maximum characters to display (default 5000)

    Returns:
        Original text if within limit, otherwise truncated text with notice
    """
    if len(text) <= max_size:
        return text
    return text[:max_size] + "\n\n... [output truncated to prevent buffer overflow] ...\n"
