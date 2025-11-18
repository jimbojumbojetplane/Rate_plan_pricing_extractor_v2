#!/usr/bin/env python3
"""
Unified Dashboard for Canadian Mobile Plans
Combines the comparison grid view and detailed table view with navigation.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import streamlit as st

# Tier definitions with new color palette
TIERS = {
    "Basic": {
        "data_range": (0, 3),
        "price_range": (15, 35),
        "gradient": "linear-gradient(135deg, #8569C4 0%, #7069CC 100%)",
        "border_color": "#8569C4",
    },
    "Standard": {
        "data_range": (10, 50),
        "price_range": (34, 55),
        "gradient": "linear-gradient(135deg, #7069CC 0%, #5D54A2 100%)",
        "border_color": "#7069CC",
    },
    "Advanced": {
        "data_range": (60, 80),
        "price_range": (39, 70),
        "gradient": "linear-gradient(135deg, #5D54A2 0%, #36366D 100%)",
        "border_color": "#5D54A2",
    },
    "Premium": {
        "data_range": (100, 175),
        "price_range": (59, 85),
        "gradient": "linear-gradient(135deg, #36366D 0%, #141E41 100%)",
        "border_color": "#36366D",
    },
    "Elite": {
        "data_range": (200, 250),
        "price_range": (69, 105),
        "gradient": "linear-gradient(135deg, #141E41 0%, #36366D 100%)",
        "border_color": "#141E41",
    },
}

BRANDS = ["Bell", "Fido", "Freedom", "Koodo", "Rogers", "Telus", "Virgin"]

CONSOLIDATED_DIR = Path("data/consolidated")


def find_latest_consolidated() -> Path:
    """Return the most recent final_consolidated_plans_*.json file.
    
    Uses filename timestamp (YYYYMMDD_HHMMSS) for sorting to ensure consistency
    across different environments (local, GitHub, Streamlit Cloud).
    """
    # Check both consolidated directory and root
    root_files = list(Path(".").glob("final_consolidated_plans_*.json"))
    dir_files = list(CONSOLIDATED_DIR.glob("final_consolidated_plans_*.json")) if CONSOLIDATED_DIR.exists() else []
    
    all_candidates = root_files + dir_files
    
    if not all_candidates:
        raise FileNotFoundError(
            f"No consolidated files found in {CONSOLIDATED_DIR} or root directory"
        )
    
    # Extract timestamp from filename and sort by it (most recent first)
    # Format: final_consolidated_plans_YYYYMMDD_HHMMSS.json
    def extract_timestamp(path: Path) -> str:
        match = re.search(r'(\d{8}_\d{6})', path.name)
        return match.group(1) if match else "00000000_000000"
    
    # Sort by timestamp in filename (descending - most recent first)
    all_candidates.sort(key=extract_timestamp, reverse=True)
    
    return all_candidates[0]


@st.cache_data(show_spinner=False)
def load_plans_data(json_path: Path, scenario_filter: Optional[str] = None) -> List[Dict]:
    """Load and filter plans from JSON file for comparison grid.
    
    Args:
        json_path: Path to consolidated JSON file
        scenario_filter: Optional scenario name to filter by (None = all scenarios, with deduplication)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    plans = []
    seen_plans = {}  # For deduplication: key -> (plan_dict, scenario_priority)
    
    # Scenario priority: prefer 1_line_mobile_only, then 1_line_bundled, then others
    def scenario_priority(scenario_name: str) -> int:
        if scenario_name == "1_line_mobile_only":
            return 0
        elif scenario_name == "1_line_bundled":
            return 1
        elif "1_line" in scenario_name:
            return 2
        elif "2_line" in scenario_name:
            return 3
        elif "3_line" in scenario_name:
            return 4
        elif "4_line" in scenario_name:
            return 5
        else:
            return 6
    
    for brand, brand_data in data.get("brands", {}).items():
        for scenario_name, scenario in brand_data.get("scenarios", {}).items():
            # Filter by scenario if specified, otherwise include all
            if scenario_filter and scenario_name != scenario_filter:
                continue
            
            for plan in scenario.get("plans", []):
                plan_name = (plan.get("planName") or "").strip()
                if not plan_name:
                    continue
                
                price_str = plan.get("currentPrice") or plan.get("regularPrice") or ""
                price = parse_price(price_str)
                if price is None:
                    continue
                
                data_str = plan.get("dataAmount") or ""
                data_gb = parse_data_amount(data_str)
                
                tier = categorize_plan(data_gb, price)
                if not tier:
                    continue
                
                plan_dict = {
                    "brand": brand.capitalize(),
                    "planName": plan_name,
                    "dataAmount": data_str,
                    "dataGB": data_gb,
                    "price": price,
                    "priceStr": price_str,
                    "tier": tier,
                    "scenario": scenario_name,  # Include scenario for reference
                }
                
                # Create deduplication key: brand + plan name + price + data
                dedup_key = f"{brand.capitalize()}|{plan_name}|{price}|{data_gb}"
                
                # If showing all scenarios, deduplicate; otherwise add all
                if scenario_filter is None:
                    # Deduplicate: keep the plan with the best scenario priority
                    if dedup_key not in seen_plans:
                        seen_plans[dedup_key] = (plan_dict, scenario_priority(scenario_name))
                    else:
                        existing_priority = seen_plans[dedup_key][1]
                        current_priority = scenario_priority(scenario_name)
                        if current_priority < existing_priority:
                            # Replace with better scenario
                            seen_plans[dedup_key] = (plan_dict, current_priority)
                else:
                    # Single scenario: no deduplication needed
                    plans.append(plan_dict)
    
    # If we deduplicated, extract the unique plans
    if scenario_filter is None:
        plans = [plan_dict for plan_dict, _ in seen_plans.values()]
    
    return plans


@st.cache_data(show_spinner=False)
def load_plans_table(json_path: Path) -> Tuple[pd.DataFrame, dict]:
    # Cache key includes file path and modification time to auto-invalidate on file change
    """Load plan records from the consolidated JSON for detailed table."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows = []

    def _fmt_list(value):
        if isinstance(value, list):
            return ", ".join([v for v in value if v]) or ""
        return value or ""

    for brand, brand_data in data.get("brands", {}).items():
        for scenario_name, scenario in brand_data.get("scenarios", {}).items():
            for plan in scenario.get("plans", []):
                plan_name = (plan.get("planName") or "").strip()
                if not plan_name:
                    continue

                price = plan.get("currentPrice") or plan.get("regularPrice") or ""
                network = plan.get("networkSpeed") or plan.get("network") or ""
                features = plan.get("features") or []
                roaming_data = plan.get("roaming") or {}
                roaming_classification = roaming_data.get("classification") if isinstance(roaming_data, dict) else None
                rows.append(
                    {
                        "brand": brand.capitalize(),
                        "planName": plan_name,
                        "priceCurrent": price,
                        "data": plan.get("dataAmount") or "",
                        "network": network,
                        "features": _fmt_list(features),
                        "roamingClassification": roaming_classification or "",
                        "speedFeatures": _fmt_list(plan.get("speedFeatures")),
                        "roamingFeatures": _fmt_list(plan.get("roamingFeatures")),
                        "internationalTextFeatures": _fmt_list(plan.get("internationalTextFeatures")),
                        "callingFeatures": _fmt_list(plan.get("callingFeatures")),
                        "otherFeatures": _fmt_list(plan.get("otherFeatures")),
                        "scenario": scenario_name,
                    }
                )

    df = pd.DataFrame(rows).reset_index(drop=True)
    metadata = data.get("metadata", {})
    return df, metadata


def parse_data_amount(data_str: str) -> Optional[float]:
    """Parse data amount string to numeric GB value."""
    if not data_str:
        return 0.0
    
    data_str = str(data_str).strip().lower()
    
    # Handle pay-as-you-go or no data
    if any(term in data_str for term in ["pay-as-you-go", "pay as you go", "no data", "none", "n/a"]):
        return 0.0
    
    # Extract first number
    match = re.search(r"(\d+(?:\.\d+)?)", data_str)
    if not match:
        return 0.0
    
    value = float(match.group(1))
    
    # Convert MB to GB if needed
    if "mb" in data_str and "gb" not in data_str:
        value = value / 1000
    
    return value


def parse_price(price_str: str) -> Optional[float]:
    """Parse price string to numeric value."""
    if not price_str:
        return None
    
    # Convert to string and remove whitespace
    price_str = str(price_str).strip()
    
    # Extract numeric value (handles $30, $30.00, $30 per month, etc.)
    match = re.search(r"(\d+(?:\.\d+)?)", price_str)
    if match:
        return float(match.group(1))
    return None


def categorize_plan(data_gb: float, price: Optional[float]) -> Optional[str]:
    """Categorize a plan into a tier based on data and price."""
    if price is None:
        return None
    
    # First, try to match by both data and price
    for tier, config in TIERS.items():
        d_min, d_max = config["data_range"]
        p_min, p_max = config["price_range"]
        
        # Check data range
        data_match = False
        if tier == "Elite":
            data_match = data_gb >= d_min
        else:
            data_match = d_min <= data_gb <= d_max
        
        # Check price range
        price_match = p_min <= price <= p_max
        
        # If both match, this is the tier
        if data_match and price_match:
            return tier
    
    # If no exact match, categorize by data amount only
    if data_gb <= 3:
        return "Basic"
    elif 10 <= data_gb <= 50:
        return "Standard"
    elif 60 <= data_gb <= 80:
        return "Advanced"
    elif 100 <= data_gb <= 175:
        return "Premium"
    elif data_gb >= 200:
        return "Elite"
    
    # Fallback for edge cases
    if data_gb < 10:
        return "Basic"
    elif data_gb < 60:
        return "Standard"
    elif data_gb < 100:
        return "Advanced"
    elif data_gb < 200:
        return "Premium"
    else:
        return "Elite"


def get_plans_by_tier_and_brand(plans: List[Dict], selected_brands: List[str], price_range: Tuple[float, float]) -> Dict[str, Dict[str, List[Dict]]]:
    """Organize plans by tier and brand."""
    organized = {tier: {brand: [] for brand in BRANDS} for tier in TIERS.keys()}
    
    for plan in plans:
        brand = plan["brand"]
        tier = plan["tier"]
        
        if brand not in selected_brands:
            continue
        
        if not (price_range[0] <= plan["price"] <= price_range[1]):
            continue
        
        if tier in organized and brand in organized[tier]:
            organized[tier][brand].append(plan)
    
    # Sort plans within each brand by data amount
    for tier in organized:
        for brand in organized[tier]:
            organized[tier][brand].sort(key=lambda x: x["dataGB"])
    
    return organized


def render_tier_header(tier_name: str, plan_count: int, min_price: Optional[float], max_price: Optional[float]):
    """Render tier header with gradient background."""
    config = TIERS[tier_name]
    d_min, d_max = config["data_range"]
    p_min, p_max = config["price_range"]
    
    if tier_name == "Elite" or d_max == 250:
        data_range = f"{d_min}+ GB"
    else:
        data_range = f"{d_min}-{d_max} GB"
    
    price_range_str = f"${p_min}-${p_max}/mo"
    
    price_info = ""
    if min_price is not None and max_price is not None:
        price_info = f" • Actual: ${min_price:.0f}-${max_price:.0f}/mo"
    
    st.markdown(
        f"""
        <div style="
            background: {config['gradient']};
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0 15px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            <h2 style="
                color: white;
                margin: 0;
                font-size: 24px;
                font-weight: bold;
            ">{tier_name} Tier</h2>
            <p style="
                color: rgba(255,255,255,0.95);
                margin: 5px 0 0 0;
                font-size: 14px;
            ">
                Data: {data_range} • Price Range: {price_range_str}{price_info} • Plans: {plan_count}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_plan_card(plan: Dict, border_color: str):
    """Render a single plan card."""
    # Truncate plan name if too long
    plan_name = plan['planName']
    if len(plan_name) > 25:
        plan_name = plan_name[:22] + "..."
    
    st.markdown(
        f"""
        <div style="
            background: #f8f9fa;
            border-left: 3px solid {border_color};
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            word-wrap: break-word;
            overflow-wrap: break-word;
        ">
            <div style="
                font-weight: bold;
                font-size: 12px;
                color: #2d3748;
                margin-bottom: 4px;
                line-height: 1.3;
            ">{plan_name}</div>
            <div style="
                font-size: 10px;
                color: #718096;
                font-style: italic;
                margin-bottom: 4px;
            ">Mobility Only - BYOD</div>
            <div style="
                color: #5D54A2;
                font-size: 13px;
                font-weight: bold;
                margin-bottom: 4px;
            ">{plan['dataAmount'] or 'No Data'}</div>
            <div style="
                color: #36366D;
                font-size: 12px;
                font-weight: bold;
            ">{plan['priceStr']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_comparison_grid(json_path: Path):
    """Render the comparison grid view."""
    # Scenario filter
    st.sidebar.header("🔍 Filters")
    
    # Load all scenarios to show options
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_scenarios = set()
    for brand_data in data.get("brands", {}).values():
        all_scenarios.update(brand_data.get("scenarios", {}).keys())
    
    scenario_options = sorted(all_scenarios)
    
    # Default to 1_line_mobile_only for comparison grid
    default_index = 0
    if "1_line_mobile_only" in scenario_options:
        # Find index of 1_line_mobile_only in the options list
        default_index = scenario_options.index("1_line_mobile_only") + 1  # +1 because "All scenarios" is first
    
    selected_scenario = st.sidebar.selectbox(
        "Scenario",
        ["All scenarios"] + scenario_options,
        index=default_index,
        help="Filter by pricing scenario. Default: 1_line_mobile_only for comparison grid."
    )
    
    scenario_filter = None if selected_scenario == "All scenarios" else selected_scenario
    
    # Show note about comparison grid default
    if scenario_filter == "1_line_mobile_only":
        st.sidebar.info("ℹ️ **Comparison Grid** shows 1-line mobile-only plans (BYOD). Use Detailed Table view for all scenarios.")
    elif scenario_filter is None:
        st.sidebar.info("ℹ️ **All scenarios** selected: Duplicate plans are automatically deduplicated. When the same plan appears in multiple scenarios, the 1_line_mobile_only version is shown.")
    
    # Load data
    with st.spinner("Loading plans data..."):
        all_plans = load_plans_data(json_path, scenario_filter=scenario_filter)
    
    if not all_plans:
        st.warning("No plans found in the data file for the selected scenario.")
        return
    
    # Brand selector - ensure all brands are available
    available_brands = sorted(set(plan["brand"] for plan in all_plans))
    # Default to all BRANDS (not just available) to show empty columns for missing brands
    selected_brands = st.sidebar.multiselect(
        "Select Brands",
        BRANDS,
        default=BRANDS,  # Default to all 7 brands
        help="Select which brands to display. All brands are shown by default."
    )
    
    if not selected_brands:
        st.info("Please select at least one brand to display.")
        return
    
    # Price range slider
    all_prices = [plan["price"] for plan in all_plans]
    if all_prices:
        min_price_all = min(all_prices)
        max_price_all = max(all_prices)
        price_range = st.sidebar.slider(
            "Price Range ($/mo)",
            min_value=int(min_price_all),
            max_value=int(max_price_all) + 10,
            value=(int(min_price_all), int(max_price_all) + 10),
        )
    else:
        price_range = (0, 150)
    
    # Statistics
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Statistics")
    st.sidebar.metric("Total Plans", len(all_plans))
    
    # Organize plans
    organized_plans = get_plans_by_tier_and_brand(all_plans, selected_brands, price_range)
    
    # Display each tier
    for tier_name in TIERS.keys():
        tier_plans = []
        for brand_plans in organized_plans[tier_name].values():
            tier_plans.extend(brand_plans)
        
        if not tier_plans:
            continue
        
        # Calculate tier statistics
        tier_prices = [p["price"] for p in tier_plans if p["price"]]
        min_tier_price = min(tier_prices) if tier_prices else None
        max_tier_price = max(tier_prices) if tier_prices else None
        
        # Render tier header
        render_tier_header(tier_name, len(tier_plans), min_tier_price, max_tier_price)
        
        # Render brand columns - use container to ensure proper width
        with st.container():
            cols = st.columns(7, gap="small")
            config = TIERS[tier_name]
            
            for idx, brand in enumerate(BRANDS):
                with cols[idx]:
                    # Brand header
                    st.markdown(
                        f'<div class="brand-header">{brand}</div>',
                        unsafe_allow_html=True
                    )
                    
                    # Plans for this brand in this tier
                    brand_plans = organized_plans[tier_name][brand]
                    
                    if brand_plans:
                        for plan in brand_plans:
                            render_plan_card(plan, config["border_color"])
                    else:
                        st.markdown(
                            '<div class="no-plans">No plans in this tier</div>',
                            unsafe_allow_html=True
                        )
        
        # Spacing between tiers
        st.markdown("<br>", unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown(
        f"<div style='text-align: center; color: #718096; font-size: 12px; padding: 20px;'>"
        f"Total plans displayed: {len([p for p in all_plans if p['brand'] in selected_brands and price_range[0] <= p['price'] <= price_range[1]])}"
        f"</div>",
        unsafe_allow_html=True
    )


def render_detailed_table(json_path: Path):
    """Render the detailed table view."""
    with st.spinner("Loading plans..."):
        plans_df, metadata = load_plans_table(json_path)

    st.sidebar.markdown(
        f"""
**Metadata**

- Generated: {metadata.get("generated_at", "unknown")}
- Brands: {', '.join(metadata.get("brands", []))}
- Total records: {metadata.get("record_count", len(plans_df))}
"""
    )

    if plans_df.empty:
        st.warning("No plan records found in the consolidated file.")
        return

    brand_options = ["All brands"] + sorted(plans_df["brand"].unique())
    selected_brand_label = st.sidebar.selectbox("Brand", brand_options, index=0)
    if selected_brand_label == "All brands":
        brand_df = plans_df.copy()
    else:
        brand_df = plans_df[plans_df["brand"] == selected_brand_label]
    scenario_options = sorted(brand_df["scenario"].unique())
    selected_scenarios = st.sidebar.multiselect(
        "Scenarios",
        scenario_options,
        default=scenario_options,
    )

    if not selected_scenarios:
        st.info("Select at least one scenario to display.")
        return

    filtered = brand_df[brand_df["scenario"].isin(selected_scenarios)][
        [
            "brand",
            "scenario",
            "planName",
            "priceCurrent",
            "data",
            "network",
            "roamingClassification",
            "speedFeatures",
            "roamingFeatures",
            "internationalTextFeatures",
            "callingFeatures",
            "otherFeatures",
        ]
    ]

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
    )


def main():
    st.set_page_config(
        page_title="Canadian Mobile Plans Dashboard",
        page_icon="📱",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Custom CSS
    st.markdown(
        """
        <style>
        /* Main container - ensure full width and no overflow */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 100%;
        }
        
        /* Ensure content doesn't overflow */
        .stApp {
            overflow-x: auto;
        }
        
        /* Brand header styling */
        .brand-header {
            color: #141E41;
            font-weight: bold;
            font-size: 14px;
            text-transform: uppercase;
            margin-bottom: 15px;
            text-align: center;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 5px;
            word-wrap: break-word;
        }
        
        /* No plans message */
        .no-plans {
            color: #718096;
            font-style: italic;
            font-size: 13px;
            text-align: center;
            padding: 20px;
            min-height: 50px;
        }
        
        /* Plan cards - ensure they fit in columns */
        div[data-testid="column"] {
            min-width: 0;
        }
        
        /* Responsive adjustments for smaller screens */
        @media (max-width: 1400px) {
            .brand-header {
                font-size: 12px;
                padding: 6px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Navigation in sidebar
    st.sidebar.title("📱 Navigation")
    view_mode = st.sidebar.radio(
        "View Mode",
        ["Comparison Grid", "Detailed Table"],
        index=0,  # Default to Comparison Grid
        help="Choose between the tiered comparison grid or detailed table view"
    )
    
    st.sidebar.markdown("---")
    
    # File path - find latest consolidated file
    try:
        json_path = find_latest_consolidated()
        st.sidebar.info(f"📄 Using: {json_path.name}")
        
        # Add a button to clear cache and reload
        if st.sidebar.button("🔄 Refresh Data (Clear Cache)"):
            st.cache_data.clear()
            st.rerun()
    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()
    
    if not json_path.exists():
        st.error(f"File not found: {json_path}")
        st.stop()
    
    # Render based on selected view
    if view_mode == "Comparison Grid":
        st.title("📱 Canadian Mobile Plans Comparison")
        render_comparison_grid(json_path)
    else:
        st.title("📊 Carrier Rate Plan Explorer")
        render_detailed_table(json_path)


if __name__ == "__main__":
    main()


