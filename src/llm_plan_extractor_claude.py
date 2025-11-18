"""
Claude-based LLM Plan Extractor for Carrier Pricing Data
Extracts structured plan information from cleaned DOM data
Handles multiline pricing through reverse-engineering logic
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import anthropic
try:
    from dotenv import load_dotenv
    # Load project secrets from ./secrets/.env if present
    load_dotenv(dotenv_path=str(Path(__file__).resolve().parents[1] / 'secrets' / '.env'))
except Exception:
    # dotenv is optional; environment may be provided by shell
    pass


def build_extraction_prompt(
    scenario_data: Dict[str, Any],
    scenario_name: str,
    carrier: str = "TELUS",
) -> str:
    """
    Shared helper that builds the detailed extraction prompt used by both
    Anthropics (Claude) and OpenAI extractors. Keeps prompt logic in one place.
    """
    # Normalize line count
    line_count = scenario_data.get("line_count", scenario_data.get("lines", 1))
    try:
        line_count = int(line_count) if line_count not in (None, "") else 1
    except (ValueError, TypeError):
        line_count = 1

    # Normalize bundled flag
    bundled_raw = scenario_data.get("bundled", False)
    if isinstance(bundled_raw, str):
        bundled = bundled_raw.lower() == "true"
    else:
        bundled = bool(bundled_raw)

    pricing_mode = "Bundled" if bundled else "Mobile Only"

    stripped_html = scenario_data.get("raw_html", "")

    prompt = f"""
You are a mobile carrier pricing data extraction expert.
Extract structured plan information from the provided DOM/HTML data.

==================== IMPORTANT STATE CONTEXT ====================
You are analyzing a {carrier} pricing page in this SPECIFIC state:
- Number of Lines: {line_count} {'line' if line_count == 1 else 'lines'}
- Pricing Mode: {pricing_mode}
- URL: https://www.telus.com/plans
- This means: You're looking at pricing configured for {line_count} {'subscriber' if line_count == 1 else 'subscribers'}

WHAT THIS CONTEXT MEANS FOR PRICE EXTRACTION:
If line_count = 1: All prices are for 1 person
If line_count = 2: Prices show first line + add-on price for second line
  Example: "$35" (first line) and "$30" (second line) = $65 total
If line_count = 3 or 4: Similar pattern with additional lines

BUNDLED vs MOBILE-ONLY:
If {pricing_mode}: Prices include/exclude home service bundles as applicable
================================================================

SCENARIO INFORMATION:
- Carrier: {carrier}
- Scenario: {scenario_name}
- Line Count Context: {line_count} line(s)
- Bundled Context: {pricing_mode}
- This is raw DOM text content with pricing, plan names, and features.

⚠️ CRITICAL: PLAN NAME EXTRACTION ⚠️
The planName field must be a CONCISE identifier, not a feature description:
- ✅ GOOD: "40GB", "10GB data, talk & text", "Basic", "Talk and Text", "Essentials", "5G+ Complete"
- ❌ BAD: "10GB bonus data" (feature), "50 GB of data up to 150 Mbps" (description), "Unlimited Canada-wide calling" (feature)
- Look for headings, prominent labels, or short identifiers (typically 1-5 words)
- If no clear name exists, construct from: [data amount] + [type] (e.g., "10GB data, talk & text")
- Features belong in the features/speedFeatures arrays, NOT in planName

CRITICAL INSTRUCTIONS FOR PRICING:

1. MARKET PRICE (Current Price):
   - This is the price AFTER autopay discount (mandatory for all)
   - Everyone pays this price with bank/card autopay
   - Look for patterns like: "$85" followed by "per month"
   - Ignore prices shown with strikethrough or "original"
   - FOR {line_count}-LINE PRICING: Extract the TOTAL for all {line_count} line(s)

2. REGULAR PRICE:
   - The full price WITHOUT autopay discount
   - Often shown before the discounted price
   - May appear as "$95" when current is "$85"

3. BUNDLED PRICE:
   - Only applies to the FIRST/PRIMARY LINE
   - Shows additional discount when bundled with home services
   - Often appears in contexts like "Mobile & Home - Recurring discount"
   - Extract the FIRST LINE bundle discount amount (e.g., $15)

4. DATA AMOUNT:
   - Extract as provided: "100 GB", "60 GB", "360 MB"
   - Include any qualifiers: "at 5G+ Speed"
   - If "pay-as-you-go", note it explicitly

5. NETWORK/SPEED:
   - "5G+", "5G Standard", "5G", "4G LTE", etc.
   - Include any "plus" indicators

6. ROAMING:
   - Note if included (e.g., "Easy Roam from $5/day")
   - List supported countries/regions
   - Classify roaming coverage into one of these categories:
     * "Canada Only" - if roaming is limited to Canada only
     * "Canada+US" - if roaming includes Canada and United States
     * "Canada+US+International" - if roaming includes Canada, US, and additional countries (specify count if mentioned, e.g., "Canada+US+27 countries")
     * null - if no roaming information is available

7. FEATURE BUCKETS (keep each list concise, max 3 items each):
   a) speedFeatures — data speeds/throttling (e.g., "Data at up to 250 Mbps", "5G throttles to 512 Kbps thereafter")
   b) roamingFeatures — roaming programs, travel add-ons, country lists (e.g., "Easy Roam from $5/day", "Canada/U.S./Mexico roaming")
   c) internationalTextFeatures — outbound/inbound international SMS allowances
   d) callingFeatures — Canada/U.S./international calling allowances
   e) otherFeatures — everything else (hotspot, streaming quality, price lock wording, promos that describe plan benefits)
   - Do NOT duplicate `networkSpeed` or pricing details inside these lists.
   - If a bucket has no relevant content, return an empty array.

8. BONUS OFFERS:
   - Any special promotions or rate locks
   - "5-Year Rate Plan Price Lock", "45-Year" mention
   - Data sharing offers, etc.

⚠️ CRITICAL EXTRACTION REQUIREMENT ⚠️
Extract ALL UNIQUE plans from the HTML below:
- Plans marked as "VALUE PLAN" or promotional offers
- Plans with similar names (e.g., "Complete" vs "Complete Explore" are DIFFERENT plans)
- All distinct rate plans with ANY different pricing or features

**🚨 MOST CRITICAL RULE - PRICE OR DATA DIFFERENCES = SEPARATE PLANS 🚨**
**If two plans have DIFFERENT PRICES OR DIFFERENT DATA AMOUNTS, they are ALWAYS SEPARATE PLANS, even if they have:**
- The SAME plan name
- Similar features

**CRITICAL: Plans with SAME name but DIFFERENT data amounts OR DIFFERENT prices are ALWAYS SEPARATE PLANS**
Examples:
  - Plan "X" at $45/mo and Plan "X" at $50/mo = TWO SEPARATE PLANS (extract both)
  - Plan "Y" with 60 GB and Plan "Y" with 100 GB = TWO SEPARATE PLANS (extract both)
  - Plan "Z" 60 GB at $70/mo and Plan "Z" 100 GB at $75/mo = TWO SEPARATE PLANS (extract both)
**If the data amount OR price differs, they are DIFFERENT plans - extract BOTH.**

**DEDUPLICATION RULE - ONLY FOR TRUE DUPLICATES**: 
The HTML may contain duplicate tiles for display purposes. You MUST deduplicate ONLY when:
- Multiple HTML tiles have IDENTICAL plan name AND IDENTICAL price AND IDENTICAL data amount AND IDENTICAL features
- Example: If you see "Essentials" 60 GB at $70/mo appearing 4 times in the HTML with identical features, extract it ONCE (index: 1)
- Example: If you see "Essentials" 100 GB at $75/mo appearing 4 times in the HTML with identical features, extract it ONCE (index: 2)
- DO NOT create separate entries for duplicate HTML tiles - they are the SAME plan displayed multiple times

**IMPORTANT DISTINCTION**:
- Same name + SAME data + SAME price + SAME features = ONE plan (deduplicate all duplicates)
- Same name + DIFFERENT price = MULTIPLE plans (extract all variants)
- Same name + DIFFERENT data = MULTIPLE plans (extract all variants)

**⚠️ CRITICAL: DO NOT CREATE PLANS THAT DO NOT EXIST ⚠️**
- Only extract plans that are clearly present in the HTML as `<div class="plan">` blocks
- Each plan MUST have a clear plan name (h2 heading), price, and data amount
- Do NOT extract section headings like "All plans include:", "Internet Members only", "Warning", etc. as plans
- Do NOT infer or create plans based on patterns or assumptions
- Do NOT create plans with prices or data amounts that are not explicitly shown in the HTML
- If a plan is not explicitly shown with a price and data amount in a `<div class="plan">` block, do not extract it
- Count the number of `<div class="plan">` blocks in the HTML - that is the EXACT number of plans to extract
- Example: If there are 6 `<div class="plan">` blocks, extract exactly 6 plans, no more, no less

STRIPPED HTML CONTENT TO ANALYZE:
==================================
{stripped_html}

REQUIRED OUTPUT JSON STRUCTURE:
{{
  "scenario": "{scenario_name}",
  "carrier": "{carrier}",
  "line_count": {line_count},
  "bundled": {str(bundled).lower()},
  "state_context": "{line_count}-line {pricing_mode}",
  "extraction_notes": "brief notes on any ambiguities",
  "plans": [
    {{
      "index": 1,
      "planName": "exact plan name from DOM",
      "regularPrice": "$XX",
      "currentPrice": "$XX per month",
      "bundledPrice": {{"firstLineDiscount": "$X"}},
      "dataAmount": "XXX GB|MB|pay-as-you-go",
      "networkSpeed": "5G+|5G|4G LTE",
      "roaming": {{
        "included": true,
        "details": "Easy Roam from $5/day",
        "countries": "27 international destinations",
        "classification": "Canada+US+International"
      }},
      "speedFeatures": ["Data at up to 250 Mbps"],
      "roamingFeatures": ["Easy Roam from $5/day in 27 countries"],
      "internationalTextFeatures": ["Unlimited international texting from Canada"],
      "callingFeatures": ["Unlimited Canada/U.S. calling"],
      "otherFeatures": ["Hotspot included", "SD video streaming"],
      "bonusOffers": [
        "5-Year Rate Plan Price Lock",
        "Other offer"
      ],
      "otherIdentifiers": {{
        "marketingLabel": "ONLY AT TELUS|VALUE PLAN|MOBILITY PLAN",
        "dataTestId": "mfe-rate-plan-tile-...",
        "originalText": "raw text snippet for verification"
      }}
    }}
  ]
}}

IMPORTANT: 
- Use sequential numbers starting from 1 for "index" field (1, 2, 3, etc.)
- Use null (lowercase) for any missing/unknown fields, NOT the string "null" or empty strings
- If bundledPrice is not available, use null instead of an empty object
- If roaming details are not available, use null for "details", "countries", and "classification" fields
- For roaming classification, analyze the countries/regions mentioned:
  * If only Canada is mentioned → "Canada Only"
  * If Canada and US are mentioned (no other countries) → "Canada+US"
  * If Canada, US, and additional countries are mentioned → "Canada+US+International" (or "Canada+US+X countries" if count is specified)
- If bonusOffers array is empty, use an empty array [] not null
- All string values must use double quotes, never single quotes

⚠️ CRITICAL JSON FORMAT REQUIREMENTS ⚠️
You MUST output valid, strict JSON that can be parsed by JSON.parse():
- ALL property names MUST be enclosed in double quotes (e.g., "planName" not planName)
- NO trailing commas before }} or ]]
- Use double quotes for ALL strings, never single quotes
- Use true/false (lowercase) for booleans, not True/False
- Use null (lowercase) for null values, not NULL or None
- Escape special characters in strings (\\, ", newlines)
- Output ONLY the JSON object, no markdown code blocks, no explanations before/after

EXTRACTION GUIDELINES:

**PLAN NAME EXTRACTION - CRITICAL**:
- Plan names should be CONCISE and IDENTIFY the plan, not describe features
- GOOD plan names: "40GB", "10GB data, talk & text", "Basic", "Talk and Text", "Essentials", "5G+ Complete"
- BAD plan names: "10GB bonus data" (this is a feature, not the plan name), "50 GB of data up to 150 Mbps" (this is a description)
- Look for:
  * Headings (h1, h2, h3) that identify the plan
  * Prominent text that appears before price/data (usually the plan identifier)
  * Short, distinctive names (1-5 words typically)
- Avoid using:
  * Feature descriptions as plan names (e.g., "Unlimited Canada-wide calling" is a feature, not a plan name)
  * Speed/network descriptions as plan names (e.g., "Data at up to 150 Mbps" is a feature)
  * Promotional text as plan names (e.g., "bonus data", "included", "special offer")
- If a plan has a clear heading/name, use that. If not, construct from data amount + type (e.g., "10GB data, talk & text")
- When in doubt, prefer shorter, more generic names over long descriptive text

**GENERAL EXTRACTION**:
- IMPORTANT: Extract ALL distinct plans, even if they have similar names (e.g., "5G+ Complete" and "5G+ Complete Explore" are DIFFERENT plans)
- CRITICAL: If two plans have the SAME name but DIFFERENT data amounts OR DIFFERENT prices, extract them as TWO SEPARATE plans
  Example: Plan "X" 60 GB at $70/mo and Plan "X" 100 GB at $75/mo = Extract BOTH as separate entries
- Count the number of unique <div class="plan"> blocks in the HTML - you should extract at least one plan per unique block (unless they are true duplicates with identical name, price, data, and features)
- Be conservative: only extract information that is clearly present in the HTML
- ⚠️ DO NOT CREATE PLANS THAT DO NOT EXIST: Only extract plans that are explicitly shown in the HTML as `<div class="plan">` blocks with clear plan name (h2), price, and data amount. Do NOT extract section headings or promotional text as plans. Count the `<div class="plan">` blocks - that is the exact number of plans to extract.
- For ambiguous pricing, note in extraction_notes
- Preserve exact wording for plan names when they are clear identifiers (do not skip plans with similar names)
- Include ALL plans that have different names OR different pricing OR different data amounts
- Include all identifiers that might help in DB matching
- If field is unknown/not mentioned, use null
- Use the state context ({line_count}-line {pricing_mode}) to help disambiguate prices
- Remember: Plans with same name + different data = DIFFERENT plans (extract both)
- Remember: Plans with same name + different price = DIFFERENT plans (extract both)

Now extract the plans from the provided DOM data:
"""
    return prompt


class ClaudePlanExtractor:
    """
    Extracts structured pricing plan data from carrier DOM using Claude API.
    Designed to handle multiline pricing scenarios and bundled discounts.
    """
    
    def __init__(self, api_key: str = None, carrier: str = "telus", model: str = "claude-3-haiku-20240307"):
        """Initialize Claude client with API key"""
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment "
                "variable or pass it to constructor."
            )
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        
        # Carrier-specific output directory
        carrier_lower = carrier.lower()
        self.output_dir = Path(f"./data/{carrier_lower}/output/llm_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Token tracking
        self.token_stats = {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'requests_count': 0,
        }
    
    def _create_extraction_prompt(
        self,
        scenario_data: Dict[str, Any],
        scenario_name: str,
        carrier: str = "TELUS",
    ) -> str:
        return build_extraction_prompt(scenario_data, scenario_name, carrier)
    
    def extract_scenario(self, scenario_data: Dict[str, Any], 
                        scenario_name: str, carrier: str = "TELUS") -> Dict[str, Any]:
        """
        Submit a single scenario to Claude for extraction.
        Returns structured plan data.
        """
        print(f"\n📤 Extracting: {scenario_name}")
        print(f"   Plans in scenario: {scenario_data.get('total_plans', 'unknown')}")
        
        prompt = self._create_extraction_prompt(scenario_data, scenario_name, carrier)
        
        try:
            # Call API with retry/backoff to handle rate limits
            # Note: response_format requires newer Anthropic SDK - using prompt instructions instead
            message = self._call_with_retries(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track tokens
            self.token_stats['total_input_tokens'] += message.usage.input_tokens
            self.token_stats['total_output_tokens'] += message.usage.output_tokens
            self.token_stats['requests_count'] += 1
            
            print(f"   ✓ Input tokens:  {message.usage.input_tokens:,}")
            print(f"   ✓ Output tokens: {message.usage.output_tokens:,}")
            
            # STEP 1: Get Claude's text response (this always succeeds)
            response_text = message.content[0].text
            print(f"   📝 Received response from Claude ({len(response_text)} chars)")
            
            # STEP 2: Parse Claude's JSON response 
            # ⚠️ PARSING ERROR OCCURS HERE if Claude returns malformed JSON
            try:
                extracted_data = self._parse_response(response_text)
                print(f"   ✅ Successfully parsed JSON from Claude's response")
            except ValueError as parse_error:
                # Show first 500 chars of response for debugging
                preview = response_text[:500].replace('\n', ' ')
                print(f"   ❌ JSON PARSE ERROR at line 250 (_parse_response call)")
                print(f"   ❌ Error: {str(parse_error)}")
                print(f"   ❌ Response preview: {preview}...")
                raise  # Re-raise to be caught by outer handler
            
            return {
                'success': True,
                'scenario': scenario_name,
                'data': extracted_data,
                'raw_response': response_text,
                'tokens': {
                    'input': message.usage.input_tokens,
                    'output': message.usage.output_tokens
                }
            }
            
        except anthropic.APIError as e:
            print(f"   ❌ API Error: {str(e)}")
            return {
                'success': False,
                'scenario': scenario_name,
                'error': f'API Error: {str(e)}'
            }
        except ValueError as e:
            # JSON parsing errors from _parse_response
            print(f"   ❌ JSON Parse Error: {str(e)}")
            return {
                'success': False,
                'scenario': scenario_name,
                'error': f'JSON Parse Error: {str(e)}'
            }
        except Exception as e:
            # Catch any other unexpected errors
            print(f"   ❌ Unexpected Error: {str(e)}")
            return {
                'success': False,
                'scenario': scenario_name,
                'error': f'Unexpected Error: {str(e)}'
            }

    def _call_with_retries(self, **kwargs):
        """
        Wrapper around anthropic client call with exponential backoff on rate limits/network errors.
        """
        max_retries = 5
        base_delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                return self.client.messages.create(**kwargs)
            except anthropic.RateLimitError as e:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** (attempt - 1))
                delay = min(delay, 60)
                print(f"   ⏳ Rate limited (attempt {attempt}/{max_retries}). Sleeping {delay:.1f}s...")
                time.sleep(delay)
            except anthropic.APIError as e:
                # Retry transient 5xx or connection issues
                if getattr(e, 'status_code', None) and 500 <= e.status_code < 600:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay = min(delay, 30)
                    print(f"   ⏳ Server error (attempt {attempt}/{max_retries}). Sleeping {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    raise
        # Final attempt without catching
        return self.client.messages.create(**kwargs)
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse Claude's JSON response from the text.
        Handles cases where JSON might be wrapped in markdown code blocks.
        """
        import re

        def _repair_json(json_str: str) -> str:
            s = json_str.strip()
            # Remove markdown code fences
            if s.startswith('```') and s.endswith('```'):
                s = re.sub(r'^```(?:json)?', '', s, flags=re.IGNORECASE).strip()
                s = re.sub(r'```$', '', s).strip()

            # Remove JavaScript-style comments
            s = re.sub(r'//.*?\n', '\n', s)
            s = re.sub(r'/\*[\s\S]*?\*/', '', s)

            # Fix trailing commas before } or ]
            s = re.sub(r',\s*([}\]])', r'\1', s)

            # Ensure property names are quoted (simple heuristic)
            # Matches: { key: value } → { "key": value }
            s = re.sub(r'([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)\s*', r'\1"\2"\3 ', s)

            return s

        # Extract candidate JSON
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            candidate = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                raise ValueError("No JSON found in response")
            candidate = json_match.group(0)

        # Try direct parse, then repaired parse
        try:
            return json.loads(candidate)
        except Exception:
            repaired = _repair_json(candidate)
            try:
                return json.loads(repaired)
            except Exception as e:
                # As a last resort, try to locate the largest balanced JSON object
                braces = 0
                start = -1
                best = ''
                for i, ch in enumerate(response_text):
                    if ch == '{':
                        if braces == 0:
                            start = i
                        braces += 1
                    elif ch == '}':
                        braces = max(0, braces - 1)
                        if braces == 0 and start != -1:
                            segment = response_text[start:i+1]
                            try:
                                return json.loads(segment)
                            except Exception:
                                # Try repair on segment
                                seg_rep = _repair_json(segment)
                                try:
                                    return json.loads(seg_rep)
                                except Exception:
                                    pass
                raise ValueError(f"Failed to parse LLM JSON after repairs: {e}")
    
    def process_telus_scenarios(self, input_json_path: str, 
                               output_prefix: str = "llm_telus_extraction") -> Dict[str, Any]:
        """
        Process all 8 Telus scenarios sequentially.
        Returns consolidated results and statistics.
        """
        print("=" * 70)
        print("CLAUDE LLM PLAN EXTRACTOR - TELUS SCENARIOS")
        print("=" * 70)
        print(f"Input: {input_json_path}")
        
        # Load input data
        with open(input_json_path, 'r') as f:
            scenarios = json.load(f)
        
        results = {
            'carrier': 'TELUS',
            'extraction_timestamp': datetime.now().isoformat(),
            'total_scenarios': len(scenarios),
            'scenarios': {},
            'token_summary': {},
            'errors': []
        }
        
        # Process each scenario
        for scenario_name, scenario_data in scenarios.items():
            result = self.extract_scenario(scenario_data, scenario_name)
            
            if result['success']:
                results['scenarios'][scenario_name] = result['data']
            else:
                results['errors'].append({
                    'scenario': scenario_name,
                    'error': result.get('error')
                })
            
            # Small pacing delay to reduce chances of 429s
            print('   ⏳ Waiting 3s...'); time.sleep(3)
        
        # Record token usage
        results['token_summary'] = self.token_stats.copy()
        
        # Save individual extraction results
        output_file = f"{self.output_dir}/{output_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print("\n" + "=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Scenarios processed: {len(results['scenarios'])}/{results['total_scenarios']}")
        print(f"Errors: {len(results['errors'])}")
        print(f"\nToken Usage:")
        print(f"  Total input:  {self.token_stats['total_input_tokens']:,}")
        print(f"  Total output: {self.token_stats['total_output_tokens']:,}")
        print(f"  Total requests: {self.token_stats['requests_count']}")
        print(f"\nOutput saved to: {output_file}")
        
        return results
    
    def process_rogers_scenarios(self, input_json_path: str, 
                                output_prefix: str = "llm_rogers_extraction") -> Dict[str, Any]:
        """
        Process all 8 Rogers scenarios sequentially.
        Returns consolidated results and statistics.
        """
        print("=" * 70)
        print("CLAUDE LLM PLAN EXTRACTOR - ROGERS SCENARIOS")
        print("=" * 70)
        print(f"Input: {input_json_path}")
        
        # Load input data
        with open(input_json_path, 'r') as f:
            scenarios = json.load(f)
        
        results = {
            'carrier': 'Rogers',
            'extraction_timestamp': datetime.now().isoformat(),
            'total_scenarios': len(scenarios),
            'scenarios': {},
            'token_summary': {},
            'errors': []
        }
        
        # Process each scenario
        for scenario_name, scenario_data in scenarios.items():
            result = self.extract_scenario(scenario_data, scenario_name, carrier="Rogers")
            
            if result['success']:
                results['scenarios'][scenario_name] = result['data']
            else:
                results['errors'].append({
                    'scenario': scenario_name,
                    'error': result.get('error')
                })
            
            # Small pacing delay to reduce chances of 429s
            print('   ⏳ Waiting 3s...'); time.sleep(3)
        
        # Record token usage
        results['token_summary'] = self.token_stats.copy()
        
        # Save individual extraction results
        output_file = f"{self.output_dir}/{output_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print("\n" + "=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Scenarios processed: {len(results['scenarios'])}/{results['total_scenarios']}")
        print(f"Errors: {len(results['errors'])}")
        print(f"\nToken Usage:")
        print(f"  Total input:  {self.token_stats['total_input_tokens']:,}")
        print(f"  Total output: {self.token_stats['total_output_tokens']:,}")
        print(f"  Total requests: {self.token_stats['requests_count']}")
        print(f"\nOutput saved to: {output_file}")
        
        return results
    
    def process_stripped_html(self, stripped_html_path: str, 
                             scenario_name: str, carrier: str = "Freedom") -> Dict[str, Any]:
        """
        Process a single stripped HTML file from the new scrapers.
        Returns structured plan data.
        """
        print(f"\n📤 Processing stripped HTML: {scenario_name}")
        print(f"   Carrier: {carrier}")
        print(f"   File: {stripped_html_path}")
        
        # Read the stripped HTML file
        with open(stripped_html_path, 'r') as f:
            stripped_html = f.read()
        
        # Create scenario data structure
        scenario_data = {
            'raw_html': stripped_html,
            'scenario_name': scenario_name,
            'carrier': carrier
        }
        
        # Extract the plan data
        result = self.extract_scenario(scenario_data, scenario_name, carrier)
        
        if result['success']:
            # Save individual result
            output_file = f"{self.output_dir}/{carrier.lower()}_{scenario_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(result['data'], f, indent=2)
            
            print(f"   ✓ Output saved to: {output_file}")
            return result['data']
        else:
            print(f"   ❌ Extraction failed: {result.get('error')}")
            return None

    def estimate_token_usage(self, scenario_data: Dict[str, Any], 
                            scenario_name: str) -> Dict[str, Any]:
        """
        Estimate token usage for a scenario without making API call.
        Uses rough approximation: ~4 characters per token.
        """
        prompt = self._create_extraction_prompt(scenario_data, scenario_name)
        estimated_input_tokens = len(prompt) // 4
        estimated_output_tokens = 3000  # Conservative estimate for JSON response
        
        return {
            'scenario': scenario_name,
            'estimated_input_tokens': estimated_input_tokens,
            'estimated_output_tokens': estimated_output_tokens,
            'estimated_total': estimated_input_tokens + estimated_output_tokens,
            'within_20_percent_limit': estimated_input_tokens < 40000  # 20% of 200K
        }


def main():
    """Example usage"""
    extractor = ClaudePlanExtractor()
    
    # Test with cleaned Telus data
    input_path = "./output/telus_smart_scraper_cleaned.json"
    
    if Path(input_path).exists():
        results = extractor.process_telus_scenarios(input_path)
        print("\n✅ Extraction complete!")
    else:
        print(f"❌ Input file not found: {input_path}")
        print("Run html_cleaner_conservative.py first to generate cleaned data.")


if __name__ == '__main__':
    main()

