"""
Advanced HTML Stripper for Rogers, Telus, Bell, Freedom, Koodo, Fido, and Virgin
Implements aggressive deduplication and semantic normalization
Target: Reduce large stripped files to minimal semantic content
NO hardcoded plan names - all extraction uses heuristics, patterns, and HTML structure
"""
import re
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Any, List, Tuple, Optional


class AdvancedHTMLStripper:
    """
    Advanced HTML stripping with plan deduplication and semantic normalization
    """
    
    @staticmethod
    def strip_rogers_html(html_content: str) -> Dict[str, Any]:
        """
        Apply all advanced stripping rules to Rogers HTML
        
        Steps:
        1. Deduplicate plan cards by (name, price, data)
        2. Strip design-system tags (ds-, dsa-)
        3. Drop CTAs (buttons)
        4. Drop footnote superscripts
        5. Drop "Price before incentives" lines
        6. Normalize feature lists (flatten nested structure)
        7. Output minimal JSON-ready HTML
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced stripping: Deduplication + semantic normalization...")
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find all plan tiles/cards
        plan_tiles = soup.select('[class*="dsa-vertical-tile"], [class*="ds-tile"], ds-tile, dsa-vertical-tile')
        
        if not plan_tiles:
            print("  ⚠️  No plan tiles found, falling back to basic stripping")
            return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
        
        print(f"  ✅ Found {len(plan_tiles)} plan tiles")
        
        # Step 2: Extract and deduplicate plans
        unique_plans = AdvancedHTMLStripper._deduplicate_plans(plan_tiles)
        print(f"  ✅ Deduplicated to {len(unique_plans)} unique plans")
        
        # Step 3: Normalize each plan
        normalized_plans = []
        for plan_data in unique_plans:
            normalized = AdvancedHTMLStripper._normalize_plan(plan_data['tile'])
            if normalized:
                normalized_plans.append(normalized)
        
        # Step 4: Build final HTML
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_tiles) if plan_tiles else 0,
                'tiles_after_dedup': len(unique_plans)
            }
        }
    
    @staticmethod
    def _deduplicate_plans(plan_tiles: List) -> List[Dict[str, Any]]:
        """
        Deduplicate plan tiles by creating keys from (name, price, data)
        Returns list of unique plan data dictionaries
        """
        seen_keys = {}
        unique_plans = []
        
        for tile in plan_tiles:
            # Extract plan_name = first meaningful <p> inside the tile
            # Plan names are: Essentials, Popular, Ultimate, etc.
            plan_name = None
            for p in tile.find_all('p'):
                text = p.get_text(strip=True)
                # Skip if empty or too short
                if not text or len(text) < 2:
                    continue
                # Skip known label text
                if text.lower() in ['features', 'plan perks', 'get 3% cash back value with a rogers red credit card', 
                                     'after auto-pay', 'price before incentives', 'rogers satellite included']:
                    continue
                # Skip if contains $ (price)
                if '$' in text:
                    continue
                # Skip if contains "per mo" or "/mo" (price)
                if 'per mo' in text.lower() or '/mo' in text.lower():
                    continue
                # Plan names are typically single capitalized words or short phrases
                # Use heuristics rather than hardcoded names for flexibility
                if text[0].isupper() and len(text) < 50:
                    # If it's a short capitalized word/phrase, treat as plan name
                    # This works for any plan name: Essentials, Popular, Ultimate, etc.
                    if len(text.split()) <= 3:
                        plan_name = text
                        break
            
            if not plan_name:
                continue
            
            # Extract price = first $NNN inside <ds-price> or <span> containing "per mo"
            price = AdvancedHTMLStripper._extract_price(tile)
            
            # Extract data_line = <li> in "Features" list containing GB or Unlimited
            data_amount = AdvancedHTMLStripper._extract_data_amount(tile)
            
            # Create deduplication key
            key = f"{plan_name}|{price}|{data_amount}"
            
            # Keep only first occurrence
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'tile': tile,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount,
                    'key': key
                })
        
        return unique_plans
    
    @staticmethod
    def _extract_price(tile) -> str:
        """Extract price from tile - first $NNN inside <ds-price> or <span> containing 'per mo'"""
        # Try ds-price first
        ds_price = tile.find('ds-price') or tile.find(class_=re.compile('price', re.I))
        if ds_price:
            price_text = ds_price.get_text()
            price_match = re.search(r'\$\d+(?:\.\d+)?', price_text)
            if price_match:
                return price_match.group(0)
        
        # Try spans with "per mo"
        spans = tile.find_all('span')
        for span in spans:
            text = span.get_text()
            if 'per mo' in text.lower():
                price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                if price_match:
                    return price_match.group(0)
        
        return "unknown"
    
    @staticmethod
    def _extract_data_amount(tile) -> str:
        """Extract data amount from Features list - <li> containing GB or Unlimited"""
        # Find Features section
        features_ul = None
        for ul in tile.find_all('ul'):
            parent_text = ul.find_parent().get_text() if ul.find_parent() else ""
            if 'features' in parent_text.lower() or 'feature' in parent_text.lower():
                features_ul = ul
                break
        
        if not features_ul:
            # Fallback: find any ul with li containing GB/Unlimited
            for ul in tile.find_all('ul'):
                for li in ul.find_all('li'):
                    text = li.get_text()
                    if re.search(r'\d+\s*GB|Unlimited', text, re.I):
                        data_match = re.search(r'(\d+\s*GB|Unlimited)', text, re.I)
                        if data_match:
                            return data_match.group(1)
            return "unknown"
        
        # Look for data line in features
        for li in features_ul.find_all('li'):
            text = li.get_text()
            if re.search(r'\d+\s*GB|Unlimited', text, re.I):
                data_match = re.search(r'(\d+\s*GB|Unlimited)', text, re.I)
                if data_match:
                    return data_match.group(1)
        
        return "unknown"
    
    @staticmethod
    def _normalize_plan(tile) -> Optional[Dict[str, Any]]:
        """Normalize a single plan tile to minimal semantic structure"""
        # Extract plan name (same logic as deduplication)
        plan_name = None
        for p in tile.find_all('p'):
            text = p.get_text(strip=True)
            if not text or len(text) < 2:
                continue
            if text.lower() in ['features', 'plan perks', 'get 3% cash back value with a rogers red credit card', 
                                 'after auto-pay', 'price before incentives', 'rogers satellite included']:
                continue
            if '$' in text or 'per mo' in text.lower() or '/mo' in text.lower():
                continue
            if text[0].isupper() and len(text) < 50:
                # Use heuristics: short capitalized word/phrase = plan name
                # This works for any plan name without hardcoding
                if len(text.split()) <= 3:
                    plan_name = text
                    break
        plan_name = plan_name or "Unknown"
        
        # Extract price details
        price_before = AdvancedHTMLStripper._extract_price_before_incentives(tile)
        price = AdvancedHTMLStripper._extract_final_price(tile)
        
        # Extract data amount and discount-specific text
        data_amount = AdvancedHTMLStripper._extract_data_amount(tile)
        features = AdvancedHTMLStripper._extract_features(tile)
        discount_keywords = ['discount', 'savings', 'price lock', 'bundle', 'family', 'per line']
        discounts = [
            feature for feature in features
            if any(keyword in feature.lower() for keyword in discount_keywords)
        ]
        
        return {
            'name': plan_name,
            'price': price,
            'regular_price': price_before,
            'data': data_amount,
            'features': [],
            'discounts': discounts[:10],
            'promotions': []
        }
    
    @staticmethod
    def _extract_final_price(tile) -> str:
        """Extract final monthly price (skip 'Price before incentives')"""
        from copy import deepcopy
        tile_copy = deepcopy(tile)
        
        # Find ds-price or price spans
        ds_price = tile_copy.find('ds-price') or tile_copy.find(class_=re.compile('price', re.I))
        if ds_price:
            price_text = ds_price.get_text()
            price_match = re.search(r'\$\d+(?:\.\d+)?(?:\s*per\s*mo|\s*/mo)?', price_text, re.I)
            if price_match:
                return price_match.group(0).strip()
        
        # Fallback: search all spans
        for span in tile_copy.find_all('span'):
            text = span.get_text()
            if 'per mo' in text.lower() or '/mo' in text.lower():
                price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                if price_match:
                    return f"{price_match.group(0)}/mo"
        
        return "unknown"
    
    @staticmethod
    def _extract_price_before_incentives(tile) -> Optional[str]:
        """Find the 'Price before incentives' string if present."""
        elem = tile.find(string=re.compile(r'Price before incentives', re.I))
        if elem:
            parent_text = elem.find_parent().get_text(" ", strip=True) if elem.find_parent() else elem
            match = re.search(r'\$\d+(?:\.\d+)?', parent_text)
            if match:
                return match.group(0)
        return None
    
    @staticmethod
    def _extract_features(tile) -> List[str]:
        """Extract and flatten features list"""
        features = []
        
        # Find Features section
        features_section = None
        for ul in tile.find_all('ul'):
            # Check if this is the features list
            parent_text = ul.find_parent().get_text() if ul.find_parent() else ""
            siblings = ul.find_previous_siblings()
            for sibling in siblings:
                if isinstance(sibling, NavigableString):
                    continue
                sibling_text = sibling.get_text() if hasattr(sibling, 'get_text') else ""
                if 'features' in sibling_text.lower() or 'feature' in sibling_text.lower():
                    features_section = ul
                    break
        
        if not features_section:
            # Fallback: find first ul with meaningful content
            for ul in tile.find_all('ul'):
                if len(ul.find_all('li')) > 2:  # Likely features
                    features_section = ul
                    break
        
        if features_section:
            # First, remove all <sup> tags from the features section
            for sup in features_section.find_all('sup'):
                sup.decompose()
            
            # Flatten nested lists and clean features
            for li in features_section.find_all('li', recursive=True):
                text = li.get_text(strip=True)
                # Skip if it's just "Features" label
                if not text or text.lower() in ['features', 'feature'] or len(text) < 3:
                    continue
                
                # Remove trailing footnote numbers (if any remain)
                text = re.sub(r'\d+$', '', text).strip()
                
                # Remove nested list markers
                text = re.sub(r'^\s*[•\-\*]\s*', '', text)
                
                # Clean up multiple spaces
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Skip duplicates
                if text and len(text) > 3 and text not in features:
                    features.append(text)
        
        return features
    
    @staticmethod
    def _extract_roaming(tile) -> Optional[str]:
        """Extract roaming information"""
        text = tile.get_text()
        roaming_match = re.search(r'roam[^.]*\.?', text, re.I)
        if roaming_match:
            return roaming_match.group(0).strip()
        return None
    
    @staticmethod
    def _extract_bonuses(tile) -> List[str]:
        """Extract bonus offers"""
        bonuses = []
        text = tile.get_text()
        
        # Look for common bonus patterns
        bonus_patterns = [
            r'Free\s+[^.]*',
            r'\d+%\s+off[^.]*',
            r'\$\d+\s+credit[^.]*',
            r'Cash\s+back[^.]*'
        ]
        
        for pattern in bonus_patterns:
            matches = re.findall(pattern, text, re.I)
            bonuses.extend(matches)
        
        return bonuses[:3]  # Limit to first 3
    
    @staticmethod
    def _build_final_html(normalized_plans: List[Dict[str, Any]]) -> str:
        """Build minimal JSON-ready HTML from normalized plans"""
        html_parts: List[str] = []
        
        for plan in normalized_plans:
            html_parts.append('<div class="plan">')
            html_parts.append(f'  <h2>{plan["name"]}</h2>')
            
            if plan.get('regular_price') and plan.get('price') and plan['regular_price'] != plan['price']:
                html_parts.append(f'  <p class="regular-price">Regular price: {plan["regular_price"]}</p>')
            
            if plan.get('price') and plan['price'] != 'unknown':
                html_parts.append(f'  <p class="price">Current price: {plan["price"]}</p>')
            
            if plan.get('bundle_price'):
                html_parts.append(f'  <p class="bundle-price">Bundled price: {plan["bundle_price"]}</p>')
            
            if plan.get('data') and plan['data'] != 'unknown':
                html_parts.append(f'  <p class="data">Data: {plan["data"]}</p>')
            
            if plan.get('network'):
                html_parts.append(f'  <p class="network">{plan["network"]}</p>')
            
            if plan.get('roaming'):
                html_parts.append(f'  <p class="roaming">{plan["roaming"]}</p>')
            
            if plan.get('features'):
                html_parts.append('  <ul class="features">')
                for feature in plan['features']:
                    # Clean feature text - remove ALL whitespace (spaces, newlines, tabs) and replace with single space
                    clean_feature = re.sub(r'\s+', ' ', str(feature)).strip()
                    # Remove any remaining newlines or tabs that might have been missed
                    clean_feature = clean_feature.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                    clean_feature = re.sub(r'\s+', ' ', clean_feature).strip()
                    if clean_feature:
                        html_parts.append(f'    <li>{clean_feature}</li>')
                html_parts.append('  </ul>')
            
            if plan.get('discounts'):
                html_parts.append('  <ul class="discounts">')
                for discount in plan['discounts']:
                    html_parts.append(f'    <li>{discount}</li>')
                html_parts.append('  </ul>')
            
            if plan.get('promotions'):
                html_parts.append('  <ul class="promotions">')
                for promo in plan['promotions']:
                    html_parts.append(f'    <li>{promo}</li>')
                html_parts.append('  </ul>')
            
            html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    @staticmethod
    def strip_telus_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Telus HTML
        
        Steps:
        1. Remove all data-testid attributes
        2. Remove all aria-* attributes
        3. Deduplicate plan tiles by (name, price, data)
        4. Remove <sup> footnotes
        5. Remove <button> elements
        6. Remove promotion callouts
        7. Remove "price before discount" sections
        8. Remove empty divs
        9. Extract ribbon text, remove wrapper
        10. Output minimal JSON-ready HTML
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Telus stripping: Attribute removal + deduplication...")
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan tiles BEFORE removing attributes (needed for deduplication)
        plan_tiles = soup.select('[data-testid*="mfe-rate-plan-tile-"][data-testid*="-container"]')
        
        # Fallback: try to find by card ID
        if not plan_tiles:
            plan_tiles = soup.select('[data-testid*="mfe-rate-plan-card-id-"]')
        
        # Step 2: Deduplicate plans BEFORE stripping attributes (need data-testid for extraction)
        unique_plans_data = AdvancedHTMLStripper._deduplicate_telus_plans(plan_tiles)
        print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans (before attribute removal)")
        
        # Step 2.5: Normalize plans BEFORE removing attributes (need data-testid for extraction)
        normalized_plans = []
        for plan_data in unique_plans_data:
            normalized = AdvancedHTMLStripper._normalize_telus_plan(plan_data['tile'])
            if normalized:
                normalized_plans.append(normalized)
        
        print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 3: Now remove attributes and clean up
        # Remove all data-testid attributes
        for tag in soup.find_all(attrs={'data-testid': True}):
            del tag['data-testid']
        
        # Remove all aria-* attributes
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        # Remove dir="auto" attributes
        for tag in soup.find_all(attrs={'dir': 'auto'}):
            del tag['dir']
        
        # Remove all <sup> footnotes
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        # Remove all <button> elements
        for button in soup.find_all('button'):
            button.decompose()
        
        # Convert promotion callouts into simple text notes rather than removing them entirely
        for div in soup.find_all('div'):
            if div.find(string=re.compile(r'Price includes savings', re.I)):
                text_content = div.get_text(" ", strip=True)
                replacement = soup.new_tag("p", **{"class": "discount-note"})
                replacement.string = text_content
                div.replace_with(replacement)
        
        # Convert "Unlock offers" sections to plain text (they contain discount context)
        for div in soup.find_all('div'):
            if div.find(string=re.compile(r'Unlock these offers', re.I)):
                text_content = div.get_text(" ", strip=True)
                replacement = soup.new_tag("p", **{"class": "discount-note"})
                replacement.string = text_content
                div.replace_with(replacement)
        
        # Remove "Full plan details" links (no pricing value)
        for div in soup.find_all('div'):
            if div.find(string=re.compile(r'Full plan details', re.I)):
                div.decompose()
        
        # Extract ribbon text, remove decorative wrappers
        for div in soup.find_all('div'):
            ribbon_texts = ['ONLY AT TELUS', 'MOBILITY PLAN', 'ROAMING DESTINATIONS']
            for ribbon_text in ribbon_texts:
                if div.find(string=re.compile(ribbon_text, re.I)):
                    text_content = div.get_text(strip=True)
                    div.clear()
                    div.string = text_content
                    break
        
        # Remove empty divs
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Step 4: Find plan tiles again after cleaning (by h3 structure)
        if not unique_plans_data:
            plan_cards = []
            for h3 in soup.find_all('h3'):
                parent = h3.find_parent('div')
                if parent and parent not in plan_cards:
                    for _ in range(3):
                        if parent and len(parent.find_all('h3')) == 1:
                            plan_cards.append(parent)
                            break
                        parent = parent.find_parent('div') if parent else None
            plan_tiles = plan_cards
            unique_plans_data = [{'tile': tile} for tile in plan_tiles]
        
        if not unique_plans_data:
            print("  ⚠️  No plan tiles found, returning cleaned HTML")
            final_html = str(soup)
            final_size = len(final_html)
            return {
                'html': final_html,
                'stats': {
                    'original_size': original_size,
                    'stripped_size': final_size,
                    'original_tokens': original_tokens,
                    'stripped_tokens': final_size // 4,
                    'tokens_saved': original_tokens - (final_size // 4),
                    'reduction_percent': round(((original_size - final_size) / original_size * 100), 2),
                    'plan_count': 0,
                    'tiles_before_dedup': 0,
                    'tiles_after_dedup': 0
                }
            }
        
        # Step 5: Build final HTML from normalized plans (already normalized before attribute removal)
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_tiles) if plan_tiles else 0,
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_telus_plans(plan_tiles: List) -> List[Dict[str, Any]]:
        """Deduplicate Telus plan tiles by (name, price, data)"""
        seen_keys = {}
        unique_plans = []
        
        for tile in plan_tiles:
            # Extract plan name from h3
            plan_name = None
            h3 = tile.find('h3')
            if h3:
                plan_name = h3.get_text(strip=True)
            
            # If no h3, try to find plan name by heuristics
            if not plan_name:
                for p in tile.find_all('p'):
                    text = p.get_text(strip=True)
                    if not text or len(text) < 2:
                        continue
                    # Skip price text
                    if '$' in text or 'per mo' in text.lower() or '/mo' in text.lower():
                        continue
                    # Skip known non-plan text
                    if text.lower() in ['features', 'unlock these offers', 'mobility plans', 'talk & text']:
                        continue
                    # Plan names are short capitalized phrases
                    if text[0].isupper() and len(text) < 50 and len(text.split()) <= 5:
                        plan_name = text
                        break
            
            if not plan_name:
                continue
            
            # Extract price from price-lockup section
            price = AdvancedHTMLStripper._extract_telus_price(tile)
            
            # Extract data amount
            data_amount = AdvancedHTMLStripper._extract_telus_data(tile)
            
            # Create deduplication key
            key = f"{plan_name}|{price}|{data_amount}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'tile': tile,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount,
                    'key': key
                })
        
        return unique_plans
    
    @staticmethod
    def _extract_telus_price(tile) -> str:
        """Extract final price from Telus tile (works with or without data-testid)"""
        # First try: look for price-lockup section by data-testid (before removal)
        price_lockup = tile.find(attrs={'data-testid': lambda x: x and 'plan-price-lockup' in str(x)})
        if price_lockup:
            price_text = price_lockup.get_text()
            price_match = re.search(r'\$\d+(?:\.\d+)?', price_text)
            if price_match:
                return price_match.group(0)
        
        # Fallback: look for price pattern in text
        text = tile.get_text()
        price_pattern = r'\$\d+(?:\.\d+)?(?:\s+per\s+month|\s+/mo)?'
        price_match = re.search(price_pattern, text, re.I)
        if price_match:
            price_str = price_match.group(0)
            return price_str.replace(' per month', '/mo').replace(' /mo', '/mo')
        
        # Last resort: find any $NN pattern
        price_match = re.search(r'\$\d+(?:\.\d+)?', text)
        if price_match:
            return price_match.group(0)
        
        return "unknown"
    
    @staticmethod
    def _extract_telus_regular_price(tile) -> Optional[str]:
        """Capture regular (pre-discount) price if displayed."""
        regular_section = tile.find(attrs={'data-testid': lambda x: x and 'plan-price-before-discounts' in str(x)})
        if regular_section:
            match = re.search(r'\$\d+(?:\.\d+)?', regular_section.get_text())
            if match:
                return match.group(0)
        # also check for strikethrough values
        strike = tile.find('s')
        if strike:
            match = re.search(r'\$\d+(?:\.\d+)?', strike.get_text())
            if match:
                return match.group(0)
        return None
    
    @staticmethod
    def _extract_telus_discount_texts(tile) -> List[str]:
        """Return discount / promotion sentences relevant to pricing."""
        discount_texts: List[str] = []
        selectors = [
            {'attrs': {'data-testid': 'promotion-callout-legal-text'}},
            {'attrs': {'data-testid': re.compile(r'promotion-benefit-text')}},
        ]
        for selector in selectors:
            for elem in tile.find_all(**selector):
                text = elem.get_text(" ", strip=True)
                if text:
                    discount_texts.append(text)
        
        # Also look for generic strings mentioning savings/discount/price lock
        keywords = ['discount', 'savings', 'price lock', 'per line', 'family']
        for text in tile.stripped_strings:
            normalized = ' '.join(text.split())
            if len(normalized) < 6:
                continue
            lower = normalized.lower()
            if any(keyword in lower for keyword in keywords):
                discount_texts.append(normalized)
        
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for entry in discount_texts:
            if entry not in seen:
                seen.add(entry)
                unique.append(entry)
        return unique[:10]
    
    @staticmethod
    def _extract_telus_data(tile) -> str:
        """Extract data amount from Telus tile (works with or without data-testid)"""
        # First try: look for data-bucket by data-testid (before removal)
        data_bucket = tile.find(attrs={'data-testid': lambda x: x and 'mfe-rate-plan-data-bucket-amount' in str(x)})
        if data_bucket:
            data_text = data_bucket.get_text(strip=True)
            # Check if there's a speed indicator nearby
            speed_bucket = tile.find(attrs={'data-testid': lambda x: x and 'mfe-rate-plan-data-bucket-speed' in str(x)})
            if speed_bucket:
                speed_text = speed_bucket.get_text(strip=True)
                if 'GB' in speed_text:
                    return f"{data_text} GB"
                return f"{data_text} {speed_text}"
            return f"{data_text} GB" if data_text.isdigit() else data_text
        
        # Fallback: search by pattern
        text = tile.get_text()
        data_match = re.search(r'(\d+\s*GB(?:\s+at\s+\d+G(?:\+)?\s+Speed)?|Unlimited)', text, re.I)
        if data_match:
            return data_match.group(1)
        
        # Last resort: simpler pattern
        data_match = re.search(r'(\d+\s*GB|Unlimited)', text, re.I)
        if data_match:
            return data_match.group(1)
        
        return "unknown"
    
    @staticmethod
    def _normalize_telus_plan(tile) -> Optional[Dict[str, Any]]:
        """Normalize a Telus plan tile to minimal structure"""
        # Extract plan name
        plan_name = "Unknown"
        h3 = tile.find('h3')
        if h3:
            plan_name = h3.get_text(strip=True)
        
        # Extract prices
        price = AdvancedHTMLStripper._extract_telus_price(tile)
        regular_price = AdvancedHTMLStripper._extract_telus_regular_price(tile)
        
        # Extract data
        data_amount = AdvancedHTMLStripper._extract_telus_data(tile)
        
        # Extract discount-focused features
        def _eligible_feature(text: str) -> bool:
            lowered = text.lower()
            return any(keyword in lowered for keyword in ['discount', 'price lock', 'per line', 'bundle', 'easy roam'])
        
        features: List[str] = []
        for li in tile.find_all('li'):
            text = li.get_text(" ", strip=True)
            if text and len(text) > 8 and _eligible_feature(text):
                features.append(text)
        
        # Collect discount snippets directly
        discounts = AdvancedHTMLStripper._extract_telus_discount_texts(tile)
        
        # Extract promotions - look for text containing "discount", "lock", "roam"
        promotions = []
        text = tile.get_text()
        promo_patterns = [
            r'\d+[- ]Year.*?Lock',
            r'Easy Roam[^.]*',
            r'discount[^.]*',
            r'Recurring discount[^.]*'
        ]
        for pattern in promo_patterns:
            matches = re.findall(pattern, text, re.I)
            promotions.extend(m[:100] for m in matches[:2])  # Limit length and count
        
        # Extract ribbon/badge text - look for known badge texts
        ribbon = None
        ribbon_texts = ['ONLY AT TELUS', 'MOBILITY PLAN', 'ROAMING DESTINATIONS']
        for ribbon_text in ribbon_texts:
            if ribbon_text in text:
                ribbon = ribbon_text
                break
        
        return {
            'name': plan_name,
            'price': price,
            'regular_price': regular_price,
            'data': data_amount,
            'features': features[:10],  # Limit features
            'promotions': promotions[:3],  # Limit promotions
            'ribbon': ribbon,
            'discounts': discounts[:10]
        }
    
    @staticmethod
    def strip_bell_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Bell HTML
        
        Steps:
        1. Find plan containers by data-product-id
        2. Deduplicate plans by (h3_name, price, data_amount) - BEFORE attribute removal
        3. Normalize plans - BEFORE attribute removal (preserve structure)
        4. Remove nav/header/footer
        5. Remove modals (aria-modal)
        6. Remove forms
        7. Remove all aria-* attributes
        8. Remove all <sup> footnotes
        9. Remove all <button> elements
        10. Remove empty divs
        11. Remove promotional text sections
        12. Remove data-same-height-* attributes
        13. Output minimal JSON-ready HTML
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Bell stripping: Deduplication + semantic normalization...")
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan containers by data-product-id (BEFORE removing anything)
        plan_containers = soup.find_all(attrs={'data-product-id': True})
        
        if not plan_containers:
            print("  ⚠️  No plan containers found, returning cleaned HTML")
            return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
        
        print(f"  ✅ Found {len(plan_containers)} plan containers")
        
        # Step 2: Deduplicate plans BEFORE removing attributes
        unique_plans_data = AdvancedHTMLStripper._deduplicate_bell_plans(plan_containers)
        print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans")
        
        # Step 3: Normalize plans BEFORE removing attributes (preserve structure)
        normalized_plans = []
        for plan_data in unique_plans_data:
            normalized = AdvancedHTMLStripper._normalize_bell_plan(plan_data['container'])
            if normalized:
                normalized_plans.append(normalized)
        
        print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 4: Remove navigation/header/footer
        for tag in soup.find_all(['nav', 'header', 'footer']):
            tag.decompose()
        
        # Step 5: Remove modals
        for modal in soup.find_all(attrs={'aria-modal': True}):
            modal.decompose()
        
        # Step 6: Remove forms (province selectors, etc.)
        for form in soup.find_all('form'):
            form.decompose()
        
        # Step 7: Remove all aria-* attributes
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        # Step 8: Remove all <sup> footnotes
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        # Step 9: Remove all <button> elements
        for button in soup.find_all('button'):
            button.decompose()
        
        # Step 10: Remove empty divs
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Step 11: Remove promotional text sections
        promo_texts = [
            'New activations only',
            'Offer ends',
            'Available 7 days a week',
            'All plans include',
            'View more plans',
            'Bring your own phone'
        ]
        for promo_text in promo_texts:
            for elem in soup.find_all(string=re.compile(re.escape(promo_text), re.I)):
                parent = elem.find_parent()
                if parent:
                    parent.decompose()
        
        # Step 12: Remove data-same-height-* attributes
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('data-same-height')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        # Step 13: Remove strikethrough prices (<s>), keep current price only
        for s_tag in soup.find_all('s'):
            s_tag.decompose()
        
        # Step 14: Remove "Average price per line" text (redundant)
        for elem in soup.find_all(string=re.compile(r'Average price per line', re.I)):
            parent = elem.find_parent()
            if parent:
                parent.decompose()
        
        # Step 15: Build final HTML from normalized plans
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_containers),
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_bell_plans(plan_containers: List) -> List[Dict[str, Any]]:
        """Deduplicate Bell plan containers by (name, price, data_amount)"""
        seen_keys = {}
        unique_plans = []
        
        for container in plan_containers:
            # Extract plan name from <h3> tag
            h3 = container.find('h3')
            plan_name = h3.get_text(strip=True) if h3 else "Unknown"
            
            # Skip non-plan containers (modals, customer questions, etc.)
            if not plan_name or len(plan_name) > 50 or '?' in plan_name:
                continue
            
            # Skip if plan name looks like a question or modal
            skip_keywords = ['are you', 'select an', 'how would', 'please select', 
                           'would you like', 'back to', 'change', 'new customer']
            plan_lower = plan_name.lower()
            if any(keyword in plan_lower for keyword in skip_keywords):
                continue
            
            # Extract data amount (heuristic: \d+ GB pattern)
            text = container.get_text()
            data_match = re.search(r'(\d+)\s*GB', text, re.I)
            data_amount = data_match.group(0) if data_match else "unknown"
            
            # Extract 1-line price (first price for deduplication)
            # Handle formats like "$105", "$105/mo", "$105/mo.", "$105.50/mo"
            price_match = re.search(r'\$\s*\d+(?:\.\d+)?(?:\s*/?\s*mo\.?)?', text)
            if price_match:
                price = price_match.group(0)
                # Clean up: remove "/mo" parts for deduplication
                price = re.sub(r'\s*/?\s*mo\.?', '', price)
                price = re.sub(r'\s+', '', price)
            else:
                price = "unknown"
            
            # Create deduplication key
            key = f"{plan_name}|{price}|{data_amount}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'container': container,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                })
        
        return unique_plans
    
    @staticmethod
    def _normalize_bell_plan(container) -> Optional[Dict[str, Any]]:
        """Normalize a single Bell plan container to minimal semantic structure"""
        # Extract plan name from <h3>
        h3 = container.find('h3')
        plan_name = h3.get_text(strip=True) if h3 else "Unknown"
        
        if not plan_name or len(plan_name) > 50 or '?' in plan_name:
            return None
        
        # Extract prices (current + regular)
        text = container.get_text(" ", strip=True)
        primary_price = "unknown"
        regular_price = None
        
        strikethrough = container.find('s')
        if strikethrough:
            match = re.search(r'\$\d+(?:\.\d+)?', strikethrough.get_text())
            if match:
                regular_price = match.group(0)
        
        price_context_pattern = r'\$\s*(\d+(?:\.\d+)?)(?:\s*/?\s*mo\.?|\s+per month)'
        price_context_match = re.search(price_context_pattern, text, re.I)
        if price_context_match:
            primary_price = f"${price_context_match.group(1)}"
        else:
            all_prices = re.findall(r'\$\s*\d+(?:\.\d+)?', text)
            meaningful_prices = [
                re.sub(r'\s+', '', p) for p in all_prices
                if re.sub(r'\s+', '', p) not in ('$0', '$0.00')
            ]
            if meaningful_prices:
                primary_price = meaningful_prices[0]
        
        # Extract data amount
        data_match = re.search(r'(\d+)\s*GB', text, re.I)
        data_amount = data_match.group(0) if data_match else "unknown"
        
        def _clean_text(value: str) -> str:
            value = re.sub(r'\s+', ' ', value).strip()
            value = re.sub(r'\bfootnote\b', '', value, flags=re.I)
            value = re.sub(r'\s+', ' ', value).strip()
            return value
        
        # Extract feature/benefit lines (network, roaming, promos, etc.)
        feature_texts: List[str] = []
        network_info: Optional[str] = None
        roaming_info: Optional[str] = None
        promotion_texts: List[str] = []
        promotion_keywords = ['offer', 'bonus', 'included', 'price lock', 'perplexity', 'promo', 'credit', 'bundle']
        feature_lists = container.select('.g-card-plan__features li') or container.find_all('li')
        
        for li in feature_lists:
            snippet = li.get_text(" ", strip=True)
            if not snippet:
                continue
            snippet = re.sub(r'\s+', ' ', snippet)
            snippet = re.sub(r'\s*\b\d+\s*$', '', snippet).strip()
            snippet = _clean_text(snippet)
            if not snippet:
                continue
            if snippet not in feature_texts:
                feature_texts.append(snippet)
            lower = snippet.lower()
            if not network_info and any(keyword in lower for keyword in ['5g', 'lte', 'network']):
                network_info = snippet
            if not roaming_info and 'roam' in lower:
                roaming_info = snippet
            if any(keyword in lower for keyword in promotion_keywords):
                promotion_texts.append(snippet)
        
        # Extract discount-focused text
        discount_keywords = ['discount', 'price lock', 'bundle', 'per line', 'savings', 'credit', 'autopay']
        discounts: List[str] = []
        for ul in container.find_all('ul'):
            ul_text = ul.get_text(" ", strip=True)
            if 'All plans include' in ul_text:
                continue
            for li in ul.find_all('li'):
                snippet = li.get_text(" ", strip=True)
                snippet = _clean_text(snippet)
                if any(keyword in snippet.lower() for keyword in discount_keywords):
                    discounts.append(snippet)
        
        # Include caption text (bundle/autopay notes) as discounts/promotions
        for caption in container.select('.g-card-plan__caption'):
            caption_text = caption.get_text(" ", strip=True)
            if not caption_text:
                continue
            caption_text = _clean_text(caption_text)
            if any(keyword in caption_text.lower() for keyword in discount_keywords):
                discounts.append(caption_text)
            else:
                promotion_texts.append(caption_text)
        
        # Deduplicate lists while preserving order
        def _dedupe(values: List[str]) -> List[str]:
            seen = set()
            deduped = []
            for value in values:
                if value and value not in seen:
                    seen.add(value)
                    deduped.append(value)
            return deduped
        
        feature_texts = _dedupe(feature_texts)
        discounts = _dedupe(discounts)
        promotion_texts = _dedupe(promotion_texts)
        
        return {
            'name': plan_name,
            'price': primary_price,
            'regular_price': regular_price,
            'data': data_amount,
            'network': network_info,
            'roaming': roaming_info,
            'features': feature_texts[:12],
            'discounts': discounts[:10],
            'promotions': promotion_texts[:5]
        }
    
    @staticmethod
    def _basic_fallback(html_content: str, original_size: int) -> Dict[str, Any]:
        """Basic fallback if no plan tiles found"""
        stripped_size = len(html_content)
        return {
            'html': html_content,
            'stats': {
                'original_size': original_size,
                'stripped_size': stripped_size,
                'original_tokens': original_size // 4,
                'stripped_tokens': stripped_size // 4,
                'tokens_saved': 0,
                'reduction_percent': 0,
                'plan_count': 0,
                'tiles_before_dedup': 0,
                'tiles_after_dedup': 0
            }
        }
    
    @staticmethod
    def strip_freedom_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Freedom HTML
        
        Steps:
        1. Find plan containers by data-testid="planComponent"
        2. Deduplicate plans by (aria-label/name, price, data_amount) - BEFORE attribute removal
        3. Normalize plans - BEFORE attribute removal
        4. Remove all aria-* attributes
        5. Remove all <sup> footnotes
        6. Remove all <button> elements
        7. Remove empty divs
        8. Output minimal JSON-ready HTML
        
        NO hardcoded plan names - uses aria-label or heuristic name extraction
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Freedom stripping: Deduplication + semantic normalization...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan containers
        plan_containers = soup.find_all(attrs={'data-testid': 'planComponent'})
        
        if not plan_containers:
            print("  ⚠️  No plan components found, returning cleaned HTML")
            return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
        
        print(f"  ✅ Found {len(plan_containers)} plan components")
        
        # Step 2: Deduplicate BEFORE removing attributes
        unique_plans_data = AdvancedHTMLStripper._deduplicate_freedom_plans(plan_containers)
        print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans")
        
        # Step 3: Normalize BEFORE removing attributes
        normalized_plans = []
        for plan_data in unique_plans_data:
            normalized = AdvancedHTMLStripper._normalize_freedom_plan(plan_data['container'])
            if normalized:
                normalized_plans.append(normalized)
        
        print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 4-7: Remove noise
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        for button in soup.find_all('button'):
            button.decompose()
        
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Step 8: Build final HTML
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_containers),
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_freedom_plans(plan_containers: List) -> List[Dict[str, Any]]:
        """Deduplicate Freedom plan containers by (name, price, data_amount)"""
        seen_keys = {}
        unique_plans = []
        
        for container in plan_containers:
            # Extract plan name from aria-label or plan-card test ID
            plan_name = container.get('aria-label', '')
            
            # Fallback: extract from plan-card data-testid
            if not plan_name:
                plan_card = container.find(attrs={'data-testid': re.compile('plan-card-', re.I)})
                if plan_card:
                    testid = plan_card.get('data-testid', '')
                    # Parse testid like "plan-card-10gb-5g" -> "10GB 5G+"
                    # Format: plan-card-{data}{unit}-{network}
                    match = re.match(r'plan-card-(\d+)(gb|mb)-?(\d+g|5g\+?|4g|lte)?', testid, re.I)
                    if match:
                        data_num = match.group(1)
                        data_unit = match.group(2).upper()
                        network = match.group(3) or ''
                        
                        # Format network (5g -> 5G+, 4g -> 4G, etc.)
                        if network:
                            network = network.upper()
                            if network == '5G':
                                network = '5G+'
                        else:
                            # Check container text for network info
                            container_text = container.get_text()
                            if re.search(r'5g\+?', container_text, re.I):
                                network = '5G+'
                            elif re.search(r'5g', container_text, re.I):
                                network = '5G'
                            elif re.search(r'4g|lte', container_text, re.I):
                                network = '4G LTE'
                        
                        # Build formatted name: "10GB 5G+"
                        if network:
                            plan_name = f"{data_num}{data_unit} {network}"
                        else:
                            plan_name = f"{data_num}{data_unit}"
                    else:
                        # Fallback: try simple extraction
                        name_match = re.search(r'plan-card-([^-]+(?:-[^-]+)?)', testid, re.I)
                        if name_match:
                            plan_name = name_match.group(1).replace('-', ' ').title()
            
            # Fallback: heuristic from headings
            if not plan_name:
                h_tags = container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                for h in h_tags:
                    text = h.get_text(strip=True)
                    if text and len(text) < 50 and not text.lower() in ['features', 'promotions', 'roaming']:
                        plan_name = text
                        break
            
            if not plan_name or len(plan_name) > 50:
                plan_name = "Unknown"
            
            # Extract data amount
            text = container.get_text()
            data_match = re.search(r'(\d+)\s*GB', text, re.I)
            data_amount = data_match.group(0) if data_match else "unknown"
            
            # Extract price (handle formats: $34/month, 34/mo, $34/mo)
            price_match = re.search(r'\$?(\d+(?:\.\d+)?)\s*(?:/|per)\s*mo(?:nth)?', text, re.I)
            if price_match:
                price = f"${price_match.group(1)}"
            else:
                price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                price = price_match.group(0) if price_match else "unknown"
            
            key = f"{plan_name}|{price}|{data_amount}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'container': container,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                })
        
        return unique_plans
    
    @staticmethod
    def _normalize_freedom_plan(container) -> Optional[Dict[str, Any]]:
        """Normalize a single Freedom plan container"""
        # Extract plan name (same as deduplication)
        plan_name = container.get('aria-label', '')
        
        if not plan_name:
            plan_card = container.find(attrs={'data-testid': re.compile('plan-card-', re.I)})
            if plan_card:
                testid = plan_card.get('data-testid', '')
                # Parse testid like "plan-card-10gb-5g" -> "10GB 5G+"
                # Format: plan-card-{data}{unit}-{network}
                match = re.match(r'plan-card-(\d+)(gb|mb)-?(\d+g|5g\+?|4g|lte)?', testid, re.I)
                if match:
                    data_num = match.group(1)
                    data_unit = match.group(2).upper()
                    network = match.group(3) or ''
                    
                    # Format network (5g -> 5G+, 4g -> 4G, etc.)
                    if network:
                        network = network.upper()
                        if network == '5G':
                            network = '5G+'
                        elif network.endswith('G') and not network.endswith('G+'):
                            network = network
                    else:
                        # Check container text for network info
                        container_text = container.get_text()
                        if re.search(r'5g\+?', container_text, re.I):
                            network = '5G+'
                        elif re.search(r'5g', container_text, re.I):
                            network = '5G'
                        elif re.search(r'4g|lte', container_text, re.I):
                            network = '4G LTE'
                    
                    # Build formatted name: "10GB 5G+"
                    if network:
                        plan_name = f"{data_num}{data_unit} {network}"
                    else:
                        plan_name = f"{data_num}{data_unit}"
                else:
                    # Fallback: try simple extraction
                    name_match = re.search(r'plan-card-([^-]+(?:-[^-]+)?)', testid, re.I)
                    if name_match:
                        plan_name = name_match.group(1).replace('-', ' ').title()
        
        if not plan_name:
            h_tags = container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            for h in h_tags:
                text = h.get_text(strip=True)
                if text and len(text) < 50 and text.lower() not in ['features', 'promotions', 'roaming']:
                    plan_name = text
                    break
        
        if not plan_name or len(plan_name) > 50:
            return None
        
        # Extract price
        text = container.get_text()
        price_match = re.search(r'\$?(\d+(?:\.\d+)?)\s*(?:/|per)\s*mo(?:nth)?', text, re.I)
        if price_match:
            price = f"${price_match.group(1)}"
        else:
            price_match = re.search(r'\$\d+(?:\.\d+)?', text)
            price = price_match.group(0) if price_match else "unknown"
        
        # Extract data amount
        data_match = re.search(r'(\d+)\s*GB', text, re.I)
        data_amount = data_match.group(0) if data_match else "unknown"
        
        # Extract features from structured sections
        features = []
        
        # Look for "Features:" section
        feature_section = None
        for h in container.find_all(['h3', 'h4']):
            if h.get_text(strip=True).lower() == 'features:':
                feature_section = h.find_parent()
                break
        
        if feature_section:
            for li in feature_section.find_all('li'):
                for sup in li.find_all('sup'):
                    sup.decompose()
                text = li.get_text(strip=True)
                if text and len(text) > 5:
                    features.append(text)
        
        # Fallback: find any ul with multiple items
        if not features:
            for ul in container.find_all('ul'):
                if len(ul.find_all('li')) >= 3:
                    for li in ul.find_all('li'):
                        for sup in li.find_all('sup'):
                            sup.decompose()
                        text = li.get_text(strip=True)
                        if text and len(text) > 5:
                            features.append(text)
                    break
        
        return {
            'name': plan_name,
            'price': price,
            'data': data_amount,
            'features': features[:15]
        }
    
    @staticmethod
    def strip_koodo_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Koodo HTML
        
        Steps:
        1. Find plan groups (Canada Wide Plans, Starter Plans)
        2. Extract group name from each group
        3. Find plan tiles within each group
        4. Deduplicate plans by (name, price, data_amount) - BEFORE attribute removal
        5. Normalize plans - BEFORE attribute removal (include group name)
        6. Remove all aria-* attributes
        7. Remove all <sup> footnotes
        8. Remove all <button> elements
        9. Remove empty divs
        10. Remove promotional text sections
        11. Output minimal JSON-ready HTML
        
        NO hardcoded plan names - constructs from data amount + speed, includes group name
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Koodo stripping: Group-aware deduplication + semantic normalization...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan groups (Koodo has "Canada Wide Plans" and "Starter Plans")
        plan_groups = soup.find_all(attrs={'data-testid': re.compile('mfe-rate-plan-tile-group', re.I)})
        # Filter to actual groups (not containers) - groups have pattern "mfe-rate-plan-tile-group-N"
        plan_groups = [g for g in plan_groups if re.search(r'mfe-rate-plan-tile-group-\d+$', g.get('data-testid', ''))]
        
        if not plan_groups:
            print("  ⚠️  No plan groups found, trying fallback method...")
            # Fallback: find plan tiles directly
            plan_tiles = soup.find_all(attrs={'data-testid': re.compile('mfe-rate-plan-tile', re.I)})
            plan_tiles = [tile for tile in plan_tiles if 'group' not in tile.get('data-testid', '').lower() and 'container' in tile.get('data-testid', '').lower()]
            
            if not plan_tiles:
                print("  ⚠️  No plan tiles found, returning cleaned HTML")
                return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
            
            print(f"  ✅ Found {len(plan_tiles)} plan tiles (fallback)")
            # Process without group context
            unique_plans_data = AdvancedHTMLStripper._deduplicate_koodo_plans(plan_tiles)
            normalized_plans = []
            for plan_data in unique_plans_data:
                normalized = AdvancedHTMLStripper._normalize_koodo_plan(plan_data['tile'], group_name=None)
                if normalized:
                    normalized_plans.append(normalized)
        else:
            print(f"  ✅ Found {len(plan_groups)} plan groups")
            
            # Step 2: Extract plan tiles from each group with group name
            all_plan_tiles_with_groups = []
            for group in plan_groups:
                # Extract group name
                group_name_elem = group.find(attrs={'data-testid': re.compile('mfe-rate-plan-group-name', re.I)})
                group_name = group_name_elem.get_text(strip=True) if group_name_elem else "Unknown"
                
                # Find tiles container within this group
                tiles_container = group.find(attrs={'data-testid': re.compile('mfe-rate-plan-tile-group-tiles-container', re.I)})
                if tiles_container:
                    # Find plan tiles in this container
                    plan_tiles = tiles_container.find_all(attrs={'data-testid': re.compile('mfe-rate-plan-tile.*container', re.I)})
                    plan_tiles = [t for t in plan_tiles if 'group' not in t.get('data-testid', '').lower()]
                    
                    print(f"    Group '{group_name}': {len(plan_tiles)} plans")
                    
                    # Associate each tile with its group
                    for tile in plan_tiles:
                        all_plan_tiles_with_groups.append({
                            'tile': tile,
                            'group_name': group_name
                        })
            
            print(f"  ✅ Total plan tiles: {len(all_plan_tiles_with_groups)}")
            
            # Step 3: Deduplicate BEFORE removing attributes (pass group context)
            unique_plans_data = AdvancedHTMLStripper._deduplicate_koodo_plans_with_groups(all_plan_tiles_with_groups)
            print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans")
            
            # Step 4: Normalize BEFORE removing attributes (include group name)
            normalized_plans = []
            for plan_data in unique_plans_data:
                normalized = AdvancedHTMLStripper._normalize_koodo_plan(plan_data['tile'], group_name=plan_data.get('group_name'))
                if normalized:
                    normalized_plans.append(normalized)
            
            print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 5-9: Remove noise
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        for button in soup.find_all('button'):
            button.decompose()
        
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Remove promotional text
        promo_texts = ['Promotion', 'Pick 1 FREE Perk', 'Price includes savings', 'See details']
        for promo_text in promo_texts:
            for elem in soup.find_all(string=re.compile(re.escape(promo_text), re.I)):
                parent = elem.find_parent()
                if parent:
                    parent.decompose()
        
        # Step 9: Build final HTML
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_tiles),
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_koodo_plans_with_groups(plan_tiles_with_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate Koodo plan tiles by (name, price, data_amount) with group context"""
        seen_keys = {}
        unique_plans = []
        
        for item in plan_tiles_with_groups:
            tile = item['tile']
            group_name = item.get('group_name', 'Unknown')
            
            # Extract data amount and speed from data-testid elements (BEFORE attribute removal)
            data_amount_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-amount', re.I)})
            data_speed_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-speed', re.I)})
            data_speed_allowance = tile.find(attrs={'data-testid': re.compile('data-bucket-speedAllowance', re.I)})
            
            data_amount = "unknown"
            speed_text = ""
            
            if data_amount_elem:
                amount = data_amount_elem.get_text(strip=True)
                if speed_allowance := (data_speed_allowance or data_speed_elem):
                    speed_text = speed_allowance.get_text(strip=True)
                # Construct data string like "110 GB" or "110 GB at 5G Speed"
                if speed_text and 'Speed' in speed_text:
                    # Extract speed from text like "at 5G Speed"
                    speed_match = re.search(r'at\s+(\d+G(?:\+)?)\s+Speed', speed_text, re.I)
                    if speed_match:
                        data_amount = f"{amount} GB at {speed_match.group(1)} Speed"
                    else:
                        data_amount = f"{amount} GB {speed_text}"
                else:
                    data_amount = f"{amount} GB" if amount.isdigit() else amount
            
            # Fallback: extract from text if data-testid not found
            if data_amount == "unknown":
                text = tile.get_text()
                data_match = re.search(r'(\d+)\s*GB(?:\s+at\s+\d+G(?:\+)?\s+Speed)?', text, re.I)
                data_amount = data_match.group(0) if data_match else "unknown"
            
            # Extract price from plan-price-lockup (BEFORE attribute removal)
            price = "unknown"
            price_elem = tile.find(attrs={'data-testid': re.compile('plan-price-lockup', re.I)})
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
                if price_match:
                    price = f"${price_match.group(1)}"
            
            # Fallback: extract from text
            if price == "unknown":
                text = tile.get_text()
                price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:per\s*month)?', text, re.I)
                if price_match:
                    price = f"${price_match.group(1)}"
            
            # Create deduplication key (use data + price + group since plans can exist in multiple groups)
            # Include group name in key to differentiate same plan in different groups
            key = f"{group_name}|{data_amount}|{price}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'tile': tile,
                    'name': data_amount if data_amount != "unknown" else "Unknown",
                    'price': price,
                    'data': data_amount,
                    'group_name': group_name
                })
        
        return unique_plans
    
    @staticmethod
    def _deduplicate_koodo_plans(plan_tiles: List) -> List[Dict[str, Any]]:
        """Deduplicate Koodo plan tiles by (name, price, data_amount)"""
        seen_keys = {}
        unique_plans = []
        
        for tile in plan_tiles:
            # Extract data amount and speed from data-testid elements (BEFORE attribute removal)
            data_amount_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-amount', re.I)})
            data_speed_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-speed', re.I)})
            data_speed_allowance = tile.find(attrs={'data-testid': re.compile('data-bucket-speedAllowance', re.I)})
            
            data_amount = "unknown"
            speed_text = ""
            
            if data_amount_elem:
                amount = data_amount_elem.get_text(strip=True)
                if speed_allowance := (data_speed_allowance or data_speed_elem):
                    speed_text = speed_allowance.get_text(strip=True)
                # Construct data string like "110 GB" or "110 GB at 5G Speed"
                if speed_text and 'Speed' in speed_text:
                    # Extract speed from text like "at 5G Speed"
                    speed_match = re.search(r'at\s+(\d+G(?:\+)?)\s+Speed', speed_text, re.I)
                    if speed_match:
                        data_amount = f"{amount} GB at {speed_match.group(1)} Speed"
                    else:
                        data_amount = f"{amount} GB {speed_text}"
                else:
                    data_amount = f"{amount} GB" if amount.isdigit() else amount
            
            # Fallback: extract from text if data-testid not found
            if data_amount == "unknown":
                text = tile.get_text()
                data_match = re.search(r'(\d+)\s*GB(?:\s+at\s+\d+G(?:\+)?\s+Speed)?', text, re.I)
                data_amount = data_match.group(0) if data_match else "unknown"
            
            # Extract price from plan-price-lockup (BEFORE attribute removal)
            price = "unknown"
            price_elem = tile.find(attrs={'data-testid': re.compile('plan-price-lockup', re.I)})
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
                if price_match:
                    price = f"${price_match.group(1)}"
            
            # Fallback: extract from text
            if price == "unknown":
                text = tile.get_text()
                price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:per\s*month)?', text, re.I)
                if price_match:
                    price = f"${price_match.group(1)}"
            
            # Construct plan name from data + speed (Koodo doesn't have explicit plan names)
            # Format: "110 GB at 5G Speed" or "110 GB"
            plan_name = data_amount if data_amount != "unknown" else "Unknown"
            
            # Create deduplication key (use data + price since plan names are constructed)
            key = f"{plan_name}|{price}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'tile': tile,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                })
        
        return unique_plans
    
    @staticmethod
    def _normalize_koodo_plan(tile, group_name: str = None) -> Optional[Dict[str, Any]]:
        """Normalize a single Koodo plan tile, optionally including group name"""
        # Extract data amount and speed from data-testid elements (BEFORE attribute removal)
        data_amount_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-amount', re.I)})
        data_speed_elem = tile.find(attrs={'data-testid': re.compile('data-bucket-speed', re.I)})
        data_speed_allowance = tile.find(attrs={'data-testid': re.compile('data-bucket-speedAllowance', re.I)})
        
        data_amount = "unknown"
        speed_text = ""
        
        if data_amount_elem:
            amount = data_amount_elem.get_text(strip=True)
            if speed_allowance := (data_speed_allowance or data_speed_elem):
                speed_text = speed_allowance.get_text(strip=True)
            
            # Construct data string
            if speed_text and 'Speed' in speed_text:
                speed_match = re.search(r'at\s+(\d+G(?:\+)?)\s+Speed', speed_text, re.I)
                if speed_match:
                    data_amount = f"{amount} GB at {speed_match.group(1)} Speed"
                else:
                    data_amount = f"{amount} GB {speed_text}"
            else:
                data_amount = f"{amount} GB" if amount.isdigit() else amount
        
        # Fallback: extract from text
        if data_amount == "unknown":
            text = tile.get_text()
            data_match = re.search(r'(\d+)\s*GB(?:\s+at\s+\d+G(?:\+)?\s+Speed)?', text, re.I)
            data_amount = data_match.group(0) if data_match else "unknown"
        
        # Construct plan name from data amount (Koodo doesn't have explicit plan names)
        # Include group name if provided (e.g., "Canada Wide Plans - 110 GB at 5G Speed")
        if group_name and group_name != "Unknown":
            plan_name = f"{group_name} - {data_amount}" if data_amount != "unknown" else f"{group_name} - Unknown"
        else:
            plan_name = data_amount if data_amount != "unknown" else "Unknown"
        
        if plan_name == "Unknown" or (plan_name.endswith("Unknown") and " - " not in plan_name):
            return None
        
        # Extract price from plan-price-lockup (BEFORE attribute removal)
        price = "unknown"
        price_elem = tile.find(attrs={'data-testid': re.compile('plan-price-lockup', re.I)})
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
            if price_match:
                price = f"${price_match.group(1)}"
        
        # Fallback: extract from text
        if price == "unknown":
            text = tile.get_text()
            price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:per\s*month)?', text, re.I)
            if price_match:
                price = f"${price_match.group(1)}"
        
        # Extract features from data-testid="mfe-rate-plan-allowance-description"
        features = []
        allowances = tile.find_all(attrs={'data-testid': re.compile('mfe-rate-plan-allowance-description', re.I)})
        
        for allowance in allowances:
            # Remove superscripts before extracting text
            from copy import copy
            allowance_copy = copy(allowance)
            for sup in allowance_copy.find_all('sup'):
                sup.decompose()
            
            # Get text and normalize spacing
            text = allowance_copy.get_text(separator=' ', strip=True)
            # Fix spacing issues (e.g., "10GBof" -> "10GB of")
            text = re.sub(r'(\d+GB)([A-Za-z])', r'\1 \2', text, flags=re.I)
            text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if text and len(text) > 5:
                # Skip if it's just the data amount (already captured)
                if not re.match(r'^\d+\s*GB', text, re.I):
                    features.append(text)
        
        # If no features found via data-testid, try ul/li fallback
        if not features:
            for ul in tile.find_all('ul'):
                for li in ul.find_all('li'):
                    for sup in li.find_all('sup'):
                        sup.decompose()
                    text = li.get_text(separator=' ', strip=True)
                    # Normalize spacing
                    text = re.sub(r'(\d+GB)([A-Za-z])', r'\1 \2', text, flags=re.I)
                    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if text and len(text) > 5:
                        features.append(text)
                if features:
                    break
        
        return {
            'name': plan_name,
            'price': price,
            'data': data_amount,
            'features': features[:15]
        }
    
    @staticmethod
    def strip_fido_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Fido HTML
        
        Steps:
        1. Find plan containers by finding spans with plan names, then their parent containers
        2. Deduplicate plans by (name, price, data_amount) - BEFORE attribute removal
        3. Normalize plans - BEFORE attribute removal
        4. Remove all aria-* attributes
        5. Remove all <sup> footnotes
        6. Remove all <button> elements
        7. Remove empty divs
        8. Remove promotional text ("Get $X off", "View more benefits")
        9. Output minimal JSON-ready HTML
        
        NO hardcoded plan names - uses span.text-title-5 for plan names
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Fido stripping: Deduplication + semantic normalization...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan containers by finding plan name spans, then walking up to ancestor with price
        # Generic rule: For each plan name span, find closest ancestor that contains a ds-price element
        plan_name_spans = soup.find_all('span', class_=re.compile('text-title-5', re.I))
        
        plan_containers = []
        for span in plan_name_spans:
            plan_name = span.get_text(strip=True)
            # Check if this looks like a plan name (generic patterns, not specific names)
            if 'BYOP' in plan_name or 'Talk & Text' in plan_name or 'GB' in plan_name or 'Complete' in plan_name:
                # Generic rule: Walk up ancestor tree to find container with ds-price element
                # This works regardless of DOM structure depth
                current = span
                found_container = None
                
                for level in range(6):  # Limit depth to prevent infinite loops
                    parent = current.find_parent(['div', 'article', 'section'])
                    if not parent:
                        break
                    
                    # Check if this ancestor contains a ds-price element (generic class pattern)
                    price_elem = parent.find(class_=re.compile('ds-price', re.I))
                    if price_elem:
                        # This ancestor has both the plan name span AND a price element
                        found_container = parent
                        break
                    
                    current = parent
                
                if found_container:
                    plan_containers.append(found_container)
        
        if not plan_containers:
            print("  ⚠️  No plan containers found, returning cleaned HTML")
            return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
        
        print(f"  ✅ Found {len(plan_containers)} plan containers")
        
        # Step 2: Deduplicate BEFORE removing attributes
        unique_plans_data = AdvancedHTMLStripper._deduplicate_fido_plans(plan_containers)
        print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans")
        
        # Step 3: Normalize BEFORE removing attributes
        normalized_plans = []
        for plan_data in unique_plans_data:
            normalized = AdvancedHTMLStripper._normalize_fido_plan(plan_data['container'])
            if normalized:
                normalized_plans.append(normalized)
        
        print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 4-8: Remove noise
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        for button in soup.find_all('button'):
            button.decompose()
        
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Remove promotional text
        promo_texts = ['Get $', 'off per month', 'View more benefits', 'Automatic Payments Discount']
        for promo_text in promo_texts:
            for elem in soup.find_all(string=re.compile(re.escape(promo_text), re.I)):
                parent = elem.find_parent()
                if parent:
                    parent.decompose()
        
        # Step 9: Build final HTML
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_containers),
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_fido_plans(plan_containers: List) -> List[Dict[str, Any]]:
        """Deduplicate Fido plan containers by (name, price, data_amount)"""
        seen_keys = {}
        unique_plans = []
        
        for container in plan_containers:
            # Extract plan name from span.text-title-5 first (Fido structure)
            plan_name = None
            plan_name_span = container.find('span', class_=re.compile('text-title-5', re.I))
            if plan_name_span:
                plan_name = plan_name_span.get_text(strip=True)
                # Remove "- BYOP Plan" suffix if present
                plan_name = plan_name.replace('- BYOP Plan', '').strip()
            
            # Fallback: Extract plan name from headings
            if not plan_name:
                for h in container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    text = h.get_text(strip=True)
                    if text and len(text) < 50 and '- BYOP Plan' not in text:
                        plan_name = text.replace('- BYOP Plan', '').strip()
                        break
            
            if not plan_name or len(plan_name) > 50:
                plan_name = "Unknown"
            
            # Extract data amount
            text = container.get_text()
            data_match = re.search(r'(\d+)\s*GB', text, re.I)
            data_amount = data_match.group(0) if data_match else "unknown"
            
            # Extract price (format: "$30.00 per mo." or "$30.00 /mo.")
            price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:per\s*mo|/mo)', text, re.I)
            if price_match:
                price = f"${price_match.group(1)}"
            else:
                price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                price = price_match.group(0) if price_match else "unknown"
            
            key = f"{plan_name}|{price}|{data_amount}"
            
            if key not in seen_keys:
                seen_keys[key] = True
                unique_plans.append({
                    'container': container,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                })
        
        return unique_plans
    
    @staticmethod
    def _normalize_fido_plan(container) -> Optional[Dict[str, Any]]:
        """Normalize a single Fido plan container"""
        # Extract plan name from span.text-title-5 first (Fido structure)
        plan_name = None
        plan_name_span = container.find('span', class_=re.compile('text-title-5', re.I))
        if plan_name_span:
            plan_name = plan_name_span.get_text(strip=True)
            # Remove "- BYOP Plan" suffix if present
            plan_name = plan_name.replace('- BYOP Plan', '').strip()
        
        # Fallback: Extract plan name from headings
        if not plan_name:
            for h in container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = h.get_text(strip=True)
                if text and len(text) < 50 and '- BYOP Plan' not in text:
                    plan_name = text.replace('- BYOP Plan', '').strip()
                    break
        
        if not plan_name or len(plan_name) > 50:
            return None
        
        # Get container text for all extractions
        text = container.get_text()
        
        # Extract price - first try ds-price element (more reliable)
        price = "unknown"
        price_elem = container.find(class_=re.compile('ds-price', re.I))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            # Extract from ds-price element (format: "$30.00 per mo." or "$30.00 /mo.")
            price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
            if price_match:
                price = f"${price_match.group(1)}"
        
        # Fallback: regex on container text
        if price == "unknown":
            price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:per\s*mo|/mo)', text, re.I)
            price = f"${price_match.group(1)}" if price_match else "unknown"
        
        # Extract data amount
        data_match = re.search(r'(\d+)\s*GB', text, re.I)
        data_amount = data_match.group(0) if data_match else "unknown"
        
        # Extract features
        features = []
        for ul in container.find_all('ul'):
            for li in ul.find_all('li'):
                for sup in li.find_all('sup'):
                    sup.decompose()
                text = li.get_text(strip=True)
                if text and len(text) > 5:
                    features.append(text)
            if features:
                break
        
        return {
            'name': plan_name,
            'price': price,
            'data': data_amount,
            'features': features[:15]
        }
    
    @staticmethod
    def strip_virgin_html(html_content: str) -> Dict[str, Any]:
        """
        Apply advanced stripping rules to Virgin HTML
        
        Steps:
        1. Find plan containers - use heuristic (divs with price + data)
        2. Deduplicate plans by (name, price, data_amount) - BEFORE attribute removal
        3. Normalize plans - BEFORE attribute removal
        4. Remove navigation/header/footer
        5. Remove all aria-* attributes
        6. Remove all <sup> footnotes
        7. Remove all <button> elements
        8. Remove empty divs
        9. Remove promotional/warning text sections
        10. Output minimal JSON-ready HTML
        
        NO hardcoded plan names - uses headings or heuristic extraction
        Virgin uses AngularJS and may not have data-testid attributes in stripped HTML
        """
        original_size = len(html_content)
        original_tokens = original_size // 4
        
        print("  🔍 Advanced Virgin stripping: Deduplication + semantic normalization...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Step 1: Find plan containers - first try plan-container elements, then fall back to heuristic
        plan_containers = []
        
        # Primary method: Look for <plan-container> elements (Angular custom elements)
        plan_container_elements = soup.find_all('plan-container')
        if plan_container_elements:
            print(f"  ✅ Found {len(plan_container_elements)} plan-container elements")
            # For each plan-container, find the inner div with class "plan"
            for pc in plan_container_elements:
                plan_div = pc.find('div', class_=re.compile(r'\bplan\b'))
                if plan_div:
                    plan_containers.append(plan_div)
                else:
                    # If no plan div found, use the plan-container itself
                    plan_containers.append(pc)
        
        # Fallback: If no plan-container elements found, use heuristic (divs containing price and optionally data)
        if not plan_containers:
            print("  ⚠️  No plan-container elements found, using heuristic method")
            all_divs = soup.find_all('div')
            
            for div in all_divs:
                text = div.get_text(strip=True)
                has_price = bool(re.search(r'\$\d+', text))
                # Look for GB, MB, or "pay per use" / "talk and text" patterns
                has_data = bool(re.search(r'\d+\s*(GB|MB)', text, re.I) or 
                               re.search(r'(pay\s*per\s*use|talk\s*and\s*text)', text, re.I))
                
                # Check if it looks like a plan container (has price, and optionally data, and reasonable size)
                if has_price and (has_data or re.search(r'(talk\s*and\s*text|basic)', text, re.I)) and 100 < len(text) < 3000:
                    # Skip if it's a large container (likely page wrapper)
                    parent_text = div.find_parent().get_text() if div.find_parent() else ""
                    if len(parent_text) < 10000:  # Reasonable parent size
                        plan_containers.append(div)
        
        if not plan_containers:
            print("  ⚠️  No plan containers found, returning cleaned HTML")
            return AdvancedHTMLStripper._basic_fallback(html_content, original_size)
        
        print(f"  ✅ Found {len(plan_containers)} plan containers")
        
        # Step 2: Deduplicate BEFORE removing attributes
        unique_plans_data = AdvancedHTMLStripper._deduplicate_virgin_plans(plan_containers)
        print(f"  ✅ Deduplicated to {len(unique_plans_data)} unique plans")
        
        # Step 3: Normalize BEFORE removing attributes
        normalized_plans = []
        for plan_data in unique_plans_data:
            normalized = AdvancedHTMLStripper._normalize_virgin_plan(plan_data['container'])
            if normalized:
                normalized_plans.append(normalized)
        
        print(f"  ✅ Normalized {len(normalized_plans)} plans")
        
        # Step 4-9: Remove noise
        for tag in soup.find_all(['nav', 'header', 'footer']):
            tag.decompose()
        
        for tag in soup.find_all():
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('aria-')]
            for attr in attrs_to_remove:
                del tag[attr]
        
        for sup in soup.find_all('sup'):
            sup.decompose()
        
        for button in soup.find_all('button'):
            button.decompose()
        
        for empty_div in soup.find_all('div'):
            if not empty_div.get_text(strip=True) and len(empty_div.find_all()) == 0:
                empty_div.decompose()
        
        # Remove promotional/warning text
        promo_texts = ['Warning Msg Title', 'Skip to', 'Find a store', 'Book an appointment', 'Log in']
        for promo_text in promo_texts:
            for elem in soup.find_all(string=re.compile(re.escape(promo_text), re.I)):
                parent = elem.find_parent()
                if parent:
                    parent.decompose()
        
        # Step 10: Build final HTML
        final_html = AdvancedHTMLStripper._build_final_html(normalized_plans)
        
        final_size = len(final_html)
        final_tokens = final_size // 4
        reduction = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
        tokens_saved = original_tokens - final_tokens
        
        print(f"  📊 Size reduction: {reduction:.1f}% ({original_size:,} → {final_size:,} chars)")
        print(f"  📊 Token reduction: {tokens_saved:,} tokens saved ({original_tokens:,} → {final_tokens:,})")
        
        return {
            'html': final_html,
            'stats': {
                'original_size': original_size,
                'stripped_size': final_size,
                'original_tokens': original_tokens,
                'stripped_tokens': final_tokens,
                'tokens_saved': tokens_saved,
                'reduction_percent': round(reduction, 2),
                'plan_count': len(normalized_plans),
                'tiles_before_dedup': len(plan_containers),
                'tiles_after_dedup': len(unique_plans_data)
            }
        }
    
    @staticmethod
    def _deduplicate_virgin_plans(plan_containers: List) -> List[Dict[str, Any]]:
        """Deduplicate Virgin plan containers by (name, price, data_amount)"""
        seen_keys = {}
        unique_plans = []
        
        for container in plan_containers:
            # First, try to extract price from accss-monthlyPrice element (most reliable)
            price = "unknown"
            price_elem = container.find(id=re.compile(r'accss-monthlyPrice-', re.I))
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
                if price_match:
                    price = f"${price_match.group(1)}"
            
            # If no price from ID, try to find it in the container text
            if price == "unknown":
                text = container.get_text()
                price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:/|per)\s*mo', text, re.I)
                if price_match:
                    price = f"${price_match.group(1)}"
                else:
                    price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                    price = price_match.group(0) if price_match else "unknown"
            
            # Extract data amount from plan.planFeatures.RP_DATA.Desc span (most reliable)
            data_amount = "unknown"
            data_span = container.find('span', class_=re.compile(r'planFeatures|RP_DATA', re.I))
            if not data_span:
                # Try finding span with data description
                for span in container.find_all('span'):
                    span_text = span.get_text(strip=True)
                    if re.search(r'\d+\s*(GB|MB)', span_text, re.I) or 'talk' in span_text.lower():
                        data_span = span
                        break
            
            if data_span:
                data_text = data_span.get_text(strip=True)
                # Look for patterns like "10GB data, talk & text", "40GB data, talk & text", "Talk and text", "250MB data, talk & text"
                data_match = re.search(r'(\d+)\s*(GB|MB)', data_text, re.I)
                if data_match:
                    data_amount = data_match.group(0)  # e.g., "10GB", "250MB"
                elif re.search(r'talk\s*and\s*text', data_text, re.I) and not re.search(r'\d+\s*(GB|MB)', data_text, re.I):
                    data_amount = "pay per use"
            
            # If still no data amount, try container text
            if data_amount == "unknown":
                text = container.get_text()
                data_match = re.search(r'(\d+)\s*(GB|MB)', text, re.I)
                if data_match:
                    data_amount = data_match.group(0)
                elif re.search(r'pay\s*per\s*use', text, re.I):
                    data_amount = "pay per use"
                elif re.search(r'talk\s*and\s*text', text, re.I) and not re.search(r'\d+\s*(GB|MB)', text, re.I):
                    data_amount = "pay per use"
            
            # Extract plan name - prioritize data description, then headings
            plan_name = None
            
            # First, try to extract from data description span
            if data_span:
                data_text = data_span.get_text(strip=True)
                # Pattern: "10GB data, talk & text" -> "10GB"
                name_match = re.search(r'(\d+GB|\d+MB)', data_text, re.I)
                if name_match:
                    plan_name = name_match.group(1)  # e.g., "10GB", "250MB"
                elif re.search(r'talk\s*and\s*text', data_text, re.I) and not re.search(r'\d+\s*(GB|MB)', data_text, re.I):
                    plan_name = "Talk and Text"
            
            # If no plan name from data span, try headings
            if not plan_name:
                for h in container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    text = h.get_text(strip=True)
                    if text and len(text) < 50:
                        # Skip headings that are not plan names
                        skip_texts = ['Warning', 'Get', 'Affordable', 'Find', 'Data, Talk and Text', 
                                     'All plans include', 'All plans', 'Plans include', 'New activations only',
                                     'Internet Members', 'Members only']
                        if not any(skip.lower() in text.lower() for skip in skip_texts):
                            plan_name = text
                            break
            
            # If still no plan name, use data amount as plan name
            if not plan_name and data_amount != "unknown":
                if data_amount in ["pay per use", "talk and text only"]:
                    plan_name = "Talk and Text"
                else:
                    plan_name = data_amount  # e.g., "10GB", "250MB"
            
            # Last resort: try to extract from container text
            if not plan_name:
                text = container.get_text()
                # Look for patterns like "10GB data, talk & text"
                name_match = re.search(r'(\d+GB)\s+data[,\s]+talk\s*[&,]\s*text', text, re.I)
                if name_match:
                    plan_name = name_match.group(1)  # e.g., "10GB"
                elif re.search(r'^talk\s*and\s*text', text[:100], re.I):
                    plan_name = "Talk and Text"
                elif re.search(r'\bbasic\b', text[:100], re.I):
                    plan_name = "Basic"
            
            # Skip if plan name is still invalid or price is unknown
            if not plan_name or plan_name == "Unknown" or len(plan_name) > 50 or price == "unknown":
                continue
            
            # Create deduplication key using price and data (most reliable)
            key = f"{price}|{data_amount}"
            
            # Also check plan name for additional uniqueness
            if key in seen_keys:
                # Check if it's the same plan or a different one
                existing = seen_keys[key]
                if existing['name'] != plan_name:
                    # Different plan with same price/data - use name in key
                    key = f"{plan_name}|{price}|{data_amount}"
            
            if key not in seen_keys:
                seen_keys[key] = {
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                }
                unique_plans.append({
                    'container': container,
                    'name': plan_name,
                    'price': price,
                    'data': data_amount
                })
        
        return unique_plans
    
    @staticmethod
    def _normalize_virgin_plan(container) -> Optional[Dict[str, Any]]:
        """Normalize a single Virgin plan container"""
        # Extract price from accss-monthlyPrice element (most reliable)
        price = "unknown"
        price_elem = container.find(id=re.compile(r'accss-monthlyPrice-', re.I))
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'\$(\d+(?:\.\d+)?)', price_text)
            if price_match:
                price = f"${price_match.group(1)}"
        
        # If no price from ID, try to find it in the container text
        if price == "unknown":
            text = container.get_text()
            price_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(?:/|per)\s*mo', text, re.I)
            if price_match:
                price = f"${price_match.group(1)}"
            else:
                price_match = re.search(r'\$\d+(?:\.\d+)?', text)
                price = price_match.group(0) if price_match else "unknown"
        
        # Extract data amount from plan.planFeatures.RP_DATA.Desc span (most reliable)
        data_amount = "unknown"
        data_span = container.find('span', class_=re.compile(r'planFeatures|RP_DATA', re.I))
        if not data_span:
            # Try finding span with data description
            for span in container.find_all('span'):
                span_text = span.get_text(strip=True)
                if re.search(r'\d+\s*(GB|MB)', span_text, re.I) or 'talk' in span_text.lower():
                    data_span = span
                    break
        
        if data_span:
            data_text = data_span.get_text(strip=True)
            # Look for patterns like "10GB data, talk & text", "40GB data, talk & text", "Talk and text", "250MB data, talk & text"
            data_match = re.search(r'(\d+)\s*(GB|MB)', data_text, re.I)
            if data_match:
                data_amount = data_match.group(0)  # e.g., "10GB", "250MB"
            elif re.search(r'talk\s*and\s*text', data_text, re.I) and not re.search(r'\d+\s*(GB|MB)', data_text, re.I):
                data_amount = "pay per use"
        
        # If still no data amount, try container text
        if data_amount == "unknown":
            text = container.get_text()
            data_match = re.search(r'(\d+)\s*(GB|MB)', text, re.I)
            if data_match:
                data_amount = data_match.group(0)
            elif re.search(r'pay\s*per\s*use', text, re.I):
                data_amount = "pay per use"
            elif re.search(r'talk\s*and\s*text', text, re.I) and not re.search(r'\d+\s*(GB|MB)', text, re.I):
                data_amount = "pay per use"
        
        # Extract plan name - prioritize data description, then headings
        plan_name = None
        
        # First, try to extract from data description span
        if data_span:
            data_text = data_span.get_text(strip=True)
            # Pattern: "10GB data, talk & text" -> "10GB"
            name_match = re.search(r'(\d+GB|\d+MB)', data_text, re.I)
            if name_match:
                plan_name = name_match.group(1)  # e.g., "10GB", "250MB"
            elif re.search(r'talk\s*and\s*text', data_text, re.I) and not re.search(r'\d+\s*(GB|MB)', data_text, re.I):
                plan_name = "Talk and Text"
        
        # If no plan name from data span, try headings
        if not plan_name:
            for h in container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = h.get_text(strip=True)
                if text and len(text) < 50:
                    skip_texts = ['Warning', 'Get', 'Affordable', 'Find', 'Data, Talk and Text',
                                 'All plans include', 'All plans', 'Plans include', 'New activations only',
                                 'Internet Members', 'Members only']
                    if not any(skip.lower() in text.lower() for skip in skip_texts):
                        plan_name = text
                        break
        
        # If still no plan name, use data amount as plan name
        if not plan_name and data_amount != "unknown":
            if data_amount in ["pay per use", "talk and text only"]:
                plan_name = "Talk and Text"
            else:
                plan_name = data_amount  # e.g., "10GB", "250MB"
        
        # Last resort: try to extract from container text
        if not plan_name:
            text = container.get_text()
            # Look for patterns like "10GB data, talk & text"
            name_match = re.search(r'(\d+GB)\s+data[,\s]+talk\s*[&,]\s*text', text, re.I)
            if name_match:
                plan_name = name_match.group(1)  # e.g., "10GB"
            elif re.search(r'^talk\s*and\s*text', text[:100], re.I):
                plan_name = "Talk and Text"
            elif re.search(r'\bbasic\b', text[:100], re.I):
                plan_name = "Basic"
        
        # Skip if plan name is still invalid or price is unknown
        if not plan_name or plan_name == "Unknown" or len(plan_name) > 50 or price == "unknown":
            return None
        
        # Extract features - clean up whitespace and noise
        features = []
        for ul in container.find_all('ul'):
            for li in ul.find_all('li'):
                for sup in li.find_all('sup'):
                    sup.decompose()
                
                # Use get_text with separator to properly handle nested content
                # separator=' ' ensures all text nodes are joined with single spaces
                text = li.get_text(separator=' ', strip=True)
                
                # Remove excessive whitespace (multiple spaces/newlines/tabs)
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Skip if too short, contains price info (already in price field), or is just whitespace
                if text and len(text) > 5:
                    # Skip if it's just a price (e.g., "$45/mo")
                    if not re.match(r'^\$?\d+.*mo', text, re.I):
                        # Skip promotional text
                        skip_patterns = ['new activations only', 'tooltip', 'view rates', 'suspicious call detection']
                        if not any(skip in text.lower() for skip in skip_patterns):
                            # If the text contains multiple sentences/phrases separated by significant whitespace,
                            # split them into separate features
                            # Look for patterns like "Feature A    Feature B" (3+ spaces) or common separators
                            parts = re.split(r'\s{3,}|\.\s+(?=[A-Z])', text)  # Split on 3+ spaces or sentence boundaries
                            for part in parts:
                                part = part.strip()
                                # Clean up any remaining whitespace
                                part = re.sub(r'\s+', ' ', part).strip()
                                if part and len(part) > 5 and part not in features:
                                    features.append(part)
            if features:
                break
        
        # Fallback: look for feature-like text patterns (only if no features found)
        if not features:
            text = container.get_text(separator=' ', strip=True)
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)
            # Look for common feature patterns
            feature_patterns = [
                r'Unlimited\s+[^.]*?',
                r'\d+\s*GB[^.]*?',
                r'Canada-wide[^.]*?',
                r'Text[^.]*?'
            ]
            for pattern in feature_patterns:
                matches = re.findall(pattern, text, re.I)
                for m in matches:
                    cleaned = m.strip()
                    if len(cleaned) > 5 and not re.match(r'^\$?\d+', cleaned):
                        features.append(cleaned)
        
        # Limit features to top 10 most relevant
        features = features[:10]
        
        return {
            'name': plan_name,
            'price': price,
            'data': data_amount,
            'features': features
        }

