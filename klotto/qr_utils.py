def parse_lotto_qr_url(url: str) -> dict:
    """
    Parse Korean Lotto QR URL
    Format: http://m.dhlottery.co.kr/?v={draw_no}m{num1}{num2}...n{num1}...
    Returns dict with 'draw_no' and 'sets' (list of lists)
    Raises ValueError if invalid
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    v_param = params.get('v', [''])[0]
    
    if not v_param:
        raise ValueError("Invalid QR format")
        
    # Split draw number and games
    parts = v_param.split('m')
    if len(parts) < 2:
        raise ValueError("Invalid format (missing 'm')")
        
    draw_no = int(parts[0])
    games_str = parts[1]
    
    # Split games ('n' separator)
    game_strs = games_str.split('n')
    
    parsed_sets = []
    for g in game_strs:
        # Each game string should be 12 digits
        clean_g = ''.join(filter(str.isdigit, g))
        if len(clean_g) < 12:
            continue
            
        nums = []
        for i in range(0, 12, 2):
            num = int(clean_g[i:i+2])
            nums.append(num)
        parsed_sets.append(sorted(nums))
    
    if not parsed_sets:
        raise ValueError("No valid numbers found")
        
    return {
        'draw_no': draw_no,
        'sets': parsed_sets
    }
