"""
Unified Multi-Carrier Pipeline Orchestrator
Refreshes raw HTML for all carriers, strips with carrier-specific logic,
submits to LLM, and creates consolidated JSON output.

Supports: Telus, Rogers, Bell, Freedom, Koodo, Fido, Virgin Plus
"""
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import concurrent.futures

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Import scrapers
from extractors.telus_dom_scraper import TelusDOMScraper
from extractors.rogers_dom_scraper import RogersDOMScraper
from extractors.bell_dom_scraper import BellDOMScraper
from extractors.freedom_dom_scraper import FreedomDOMScraper
from extractors.koodo_dom_scraper import KoodoDOMScraper
from extractors.fido_dom_scraper import FidoDOMScraper
from extractors.virgin_dom_scraper import VirginPlusDOMScraper

# Import LLM extractor
from llm_plan_extractor_claude import ClaudePlanExtractor
from llm_plan_extractor_openai import OpenAIPlanExtractor


class UnifiedPipeline:
    """
    Unified pipeline for all carriers
    Handles: Scraping → Stripping → LLM Extraction → Consolidation
    """
    
    # Carrier configuration
    CARRIERS = {
        'telus': {
            'scraper_class': TelusDOMScraper,
            'scenarios': 8,  # 1-4 lines × bundled/mobile-only
            'needs_structure_extraction': False
        },
        'rogers': {
            'scraper_class': RogersDOMScraper,
            'scenarios': 8,
            'needs_structure_extraction': False
        },
        'bell': {
            'scraper_class': BellDOMScraper,
            'scenarios': 8,
            'needs_structure_extraction': True  # Uses HTMLStructureExtractor
        },
        'freedom': {
            'scraper_class': FreedomDOMScraper,
            'scenarios': 1,
            'needs_structure_extraction': False
        },
        'koodo': {
            'scraper_class': KoodoDOMScraper,
            'scenarios': 1,
            'needs_structure_extraction': False
        },
        'fido': {
            'scraper_class': FidoDOMScraper,
            'scenarios': 1,
            'needs_structure_extraction': False
        },
        'virgin': {
            'scraper_class': VirginPlusDOMScraper,
            'scenarios': 1,
            'needs_structure_extraction': False
        }
    }
    
    def __init__(self, carriers: List[str] = None, output_base_dir: str = "./data",
                 skip_scraping: bool = False, skip_llm: bool = False,
                 llm_model: str = "gpt-5-nano", auto_push_to_github: bool = False):
        """
        Initialize unified pipeline
        
        Args:
            carriers: List of carriers to process (None = all)
            output_base_dir: Base directory for output files
            skip_scraping: Skip scraping step (use existing HTML)
            skip_llm: Skip LLM extraction step
        """
        self.output_base_dir = Path(output_base_dir)
        self.pipeline_dir = self.output_base_dir / "pipeline_runs"
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)
        
        # Select carriers to process
        self.carriers = carriers if carriers else list(self.CARRIERS.keys())
        self.skip_scraping = skip_scraping
        self.skip_llm = skip_llm
        self.llm_model = llm_model
        
        # Pipeline log
        self.event_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.auto_push_to_github = auto_push_to_github
        self.pipeline_log = {
            'timestamp_start': datetime.now().isoformat(),
            'carriers': {},
            'global_stats': {},
            'consolidated_output': None,
            'event_id': self.event_id
        }
        
        # LLM extractor will be initialized per-carrier
        self.llm_extractors = {}
    
    def run_complete_pipeline(self) -> Dict[str, Any]:
        """
        Run complete pipeline for all carriers
        Returns consolidated results
        """
        print("\n" + "="*80)
        print("🚀 UNIFIED MULTI-CARRIER PIPELINE")
        print("="*80)
        print(f"🆔 Extraction Event ID: {self.event_id}")
        print(f"📋 Carriers: {', '.join(self.carriers)}")
        print(f"⏭️  Skip scraping: {self.skip_scraping}")
        print(f"⏭️  Skip LLM: {self.skip_llm}")
        print("="*80)
        
        start_time = time.time()
        all_results = {}
        
        # Process each carrier
        for carrier in self.carriers:
            if carrier not in self.CARRIERS:
                print(f"⚠️  Unknown carrier: {carrier}, skipping")
                continue
                
            print(f"\n{'='*80}")
            print(f"📡 PROCESSING: {carrier.upper()}")
            print(f"{'='*80}")
            
            try:
                result = self._process_carrier(carrier)
                all_results[carrier] = result
                self.pipeline_log['carriers'][carrier] = result
            except Exception as e:
                print(f"❌ Error processing {carrier}: {e}")
                all_results[carrier] = {'success': False, 'error': str(e)}
        
        # Consolidate results
        consolidated = self._consolidate_results(all_results)
        self.pipeline_log['consolidated_output'] = consolidated
        
        # Save consolidated output
        self._save_consolidated_output(consolidated)
        
        # Final summary
        duration = time.time() - start_time
        self.pipeline_log['global_stats'] = {
            'total_duration': round(duration, 2),
            'carriers_processed': len(all_results),
            'successful_carriers': sum(1 for r in all_results.values() if r.get('success')),
            'timestamp_end': datetime.now().isoformat()
        }
        
        self._print_summary(all_results)
        
        # Save pipeline log
        self._save_pipeline_log()
        
        # Run consolidation steps
        print("\n" + "="*80)
        print("📦 CONSOLIDATION STEP")
        print("="*80)
        
        # Generate brand-level consolidated files
        print("\n  🔄 Generating brand-level consolidated files...")
        env = os.environ.copy()
        env['PIPELINE_EVENT_ID'] = self.event_id
        try:
            import subprocess
            import sys
            result = subprocess.run(
                [sys.executable, "scripts/generate_brand_all_plans.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=300
            )
            if result.returncode == 0:
                # Display all output lines
                for line in result.stdout.split('\n'):
                    if line.strip():
                        print(f"  {line}")
            else:
                print(f"  ⚠️  Brand consolidation script had issues: {result.stderr}")
        except Exception as e:
            print(f"  ⚠️  Error running brand consolidation: {e}")
        
        # Run final consolidation
        print("\n  🔄 Running final consolidation...")
        try:
            # Set up environment variables for consolidation script
            env = {**os.environ, "PIPELINE_EVENT_ID": self.event_id}
            if self.auto_push_to_github:
                env["AUTO_PUSH_TO_GITHUB"] = "true"
            
            result = subprocess.run(
                [sys.executable, "scripts/consolidate_llm_outputs.py"],
                capture_output=True,
                text=True,
                env=env,
                timeout=300
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Per-brand' in line or 'Global consolidated' in line:
                        print(f"  ✅ {line}")
                    elif 'Records:' in line:
                        print(f"     {line}")
                
                # Find the final consolidated file
                from pathlib import Path
                consolidated_dir = Path("data/consolidated")
                if consolidated_dir.exists():
                    files = sorted(consolidated_dir.glob("final_consolidated_plans_*.json"), reverse=True)
                    if files:
                        print(f"  ✅ FINAL CONSOLIDATED ALL CARRIERS COMPLETE")
                        print(f"     File: {files[0]}")
                        
                        # Note: Auto-push is now handled by consolidate_llm_outputs.py
                        # when AUTO_PUSH_TO_GITHUB environment variable is set
            else:
                print(f"  ⚠️  Final consolidation script had issues: {result.stderr}")
        except Exception as e:
            print(f"  ⚠️  Error running final consolidation: {e}")
        
        return consolidated
    
    def _process_carrier(self, carrier: str) -> Dict[str, Any]:
        """
        Process a single carrier through all pipeline steps
        """
        config = self.CARRIERS[carrier]
        result = {
            'carrier': carrier,
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'steps': {},
            'scenarios': {}
        }
        
        # Step 1: Scraping and Stripping
        if not self.skip_scraping:
            scrape_result = self._step_1_scrape_and_strip(carrier)
            result['steps']['scraping'] = scrape_result
            
            if not scrape_result.get('success'):
                result['error'] = 'Scraping failed'
                return result
        else:
            print("  ⏭️  Skipping scraping (using existing HTML)")
            result['steps']['scraping'] = {'success': True, 'skipped': True}
        
        # Step 2: LLM Extraction
        if not self.skip_llm:
            llm_result = self._step_2_llm_extraction(carrier, config)
            result['steps']['llm_extraction'] = llm_result
            result['scenarios'] = llm_result.get('scenarios', {})
        else:
            print("  ⏭️  Skipping LLM extraction")
            result['steps']['llm_extraction'] = {'success': True, 'skipped': True}
        
        result['success'] = True
        return result
    
    def _step_1_scrape_and_strip(self, carrier: str) -> Dict[str, Any]:
        """Step 1: Scrape raw HTML and strip for carrier"""
        print(f"  📡 Step 1: Scraping {carrier}...")
        
        try:
            scraper_class = self.CARRIERS[carrier]['scraper_class']
            scraper = scraper_class(output_base_dir=str(self.output_base_dir))
            
            # Run extraction
            extraction_results = scraper.run_extraction()
            
            # Report completion per scenario
            scenarios_data = extraction_results.get('scenarios', {})
            for scenario_name, scenario_result in scenarios_data.items():
                if scenario_result.get('success'):
                    output_file = scenario_result.get('output_file', 'unknown')
                    # Extract raw filename (output_file is stripped, raw is typically similar name)
                    raw_filename = output_file.replace('_stripped', '_raw') if '_stripped' in output_file else f"{scenario_name}_raw.html"
                    print(f"  ✅ HTML RAW EXTRACTION COMPLETE: {carrier.upper()} - {scenario_name}")
                    print(f"     File: {raw_filename}")
                    print(f"  ✅ HTML STRIPPED COMPLETE: {carrier.upper()} - {scenario_name}")
                    print(f"     File: {output_file}")
                    stripped_path = Path(output_file)
                    if not stripped_path.is_absolute():
                        stripped_path = (
                            self.output_base_dir
                            / carrier
                            / "input"
                            / "stripped_html"
                            / stripped_path
                        )
                    self._annotate_file_with_event_id(stripped_path)
                else:
                    print(f"  ❌ HTML EXTRACTION FAILED: {carrier.upper()} - {scenario_name}")
                    print(f"     Error: {scenario_result.get('error', 'Unknown error')}")
            
            return {
                'success': extraction_results.get('success', False),
                'scenarios': scenarios_data,
                'summary': extraction_results.get('summary', {})
            }
        except Exception as e:
            print(f"  ❌ Scraping failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _step_2_llm_extraction(self, carrier: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: LLM extraction for carrier"""
        print(f"  🤖 Step 2: LLM extraction for {carrier}...")
        
        try:
            # Initialize LLM extractor for this carrier
            if carrier not in self.llm_extractors:
                try:
                    if self.llm_model.lower().startswith("gpt-"):
                        extractor = OpenAIPlanExtractor(
                            carrier=carrier, model=self.llm_model
                        )
                        extractor_name = "OpenAI"
                    else:
                        extractor = ClaudePlanExtractor(
                            carrier=carrier, model=self.llm_model
                        )
                        extractor_name = "Claude"
                    self.llm_extractors[carrier] = extractor
                    print(f"  ✅ {extractor_name} extractor initialized for {carrier}")
                except Exception as e:
                    print(f"  ❌ Failed to initialize LLM extractor: {e}")
                    return {'success': False, 'error': f'LLM initialization failed: {e}'}
            
            llm_extractor = self.llm_extractors[carrier]
            
            # Load stripped HTML files
            scenarios = self._load_scenarios_for_carrier(carrier)
            
            if not scenarios:
                return {'success': False, 'error': 'No scenarios found'}
            
            # Process each scenario with LLM
            llm_results = {}
            for scenario_name, scenario_data in scenarios.items():
                print(f"    📊 Processing scenario: {scenario_name}")
                print(f"  📤 LLM SUBMISSION: {carrier.upper()} - {scenario_name}")
                
                try:
                    # Extract with LLM
                    extraction = llm_extractor.extract_scenario(
                        scenario_data=scenario_data,
                        scenario_name=scenario_name,
                        carrier=carrier.capitalize()
                    )
                    
                    if extraction.get('success'):
                        # Save LLM output to file
                        from pathlib import Path
                        import json
                        llm_out_dir = self.output_base_dir / carrier / "output" / "llm_output"
                        llm_out_dir.mkdir(parents=True, exist_ok=True)
                        
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        output_filename = f"{carrier}_{scenario_name}_{timestamp}.json"
                        output_path = llm_out_dir / output_filename
                        
                        # Save the extraction result
                        extraction_data = extraction['data']
                        extraction_data['eventId'] = self.event_id
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(extraction_data, f, indent=2, ensure_ascii=False)
                        
                        print(f"  ✅ LLM EXTRACTION COMPLETE: {carrier.upper()} - {scenario_name}")
                        print(f"     Output: {output_filename}")
                    else:
                        print(f"  ❌ LLM EXTRACTION FAILED: {carrier.upper()} - {scenario_name}")
                        print(f"     Error: {extraction.get('error', 'Unknown error')}")
                    
                    llm_results[scenario_name] = extraction
                except Exception as e:
                    print(f"    ❌ Failed to extract {scenario_name}: {e}")
                    print(f"  ❌ LLM EXTRACTION FAILED: {carrier.upper()} - {scenario_name}")
                    print(f"     Error: {str(e)}")
                    llm_results[scenario_name] = {'error': str(e)}
            
            return {
                'success': True,
                'scenarios': llm_results,
                'count': len(llm_results)
            }
        except Exception as e:
            print(f"  ❌ LLM extraction failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _load_scenarios_for_carrier(self, carrier: str) -> Dict[str, Any]:
        """Load stripped HTML files for a carrier's scenarios"""
        stripped_dir = self.output_base_dir / carrier / "input" / "stripped_html"
        
        if not stripped_dir.exists():
            return {}
        
        # Get valid scenario names from scraper configuration
        config = self.CARRIERS.get(carrier, {})
        scraper_class = config.get('scraper_class')
        valid_scenarios = set()
        
        if scraper_class:
            try:
                # Instantiate scraper to get its scenarios
                temp_scraper = scraper_class(output_base_dir=str(self.output_base_dir), 
                                            data_base_dir=str(self.output_base_dir))
                valid_scenarios = {s['name'] for s in temp_scraper.scenarios}
            except Exception:
                pass
        
        # Legacy scenario name mappings (old -> new)
        legacy_mappings = {
            'freedom': {'single_pricing': '1_line_mobile_only'},
            'fido': {'single_pricing': '1_line_mobile_only'},
            'virgin': {'single_pricing': '1_line_mobile_only'},
            'koodo': {'single_pricing': '1_line_mobile_only'},
        }
        
        scenarios = {}
        file_map = {}  # Track files by scenario name to get latest
        
        # Find all stripped HTML files
        for html_file in sorted(stripped_dir.glob(f"{carrier}_*_stripped_*.html"), reverse=True):
            # Extract scenario name from filename, removing timestamp
            # Format: carrier_scenario_name_stripped_YYYYMMDD_HHMMSS.html
            stem = html_file.stem.replace('_stripped', '')
            # Remove timestamp pattern (_YYYYMMDD_HHMMSS)
            import re
            stem_clean = re.sub(r'_\d{8}_\d{6}$', '', stem)
            parts = stem_clean.split('_', 1)
            if len(parts) == 2:
                scenario_name = parts[1]
            else:
                scenario_name = 'unknown'
            
            # Map legacy scenario names to new ones
            if carrier in legacy_mappings and scenario_name in legacy_mappings[carrier]:
                scenario_name = legacy_mappings[carrier][scenario_name]
            
            # Filter: only process valid scenarios (if we have valid_scenarios set)
            # OR if valid_scenarios is empty (backward compatibility), process all
            if valid_scenarios and scenario_name not in valid_scenarios:
                continue
            
            # Use only the latest file per scenario
            if scenario_name not in file_map:
                file_map[scenario_name] = html_file
        
        # Load only the latest file for each scenario
        for scenario_name, html_file in file_map.items():
            # Read HTML content
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Parse scenario info from comments
            scenario_data = {
                'scenario_name': scenario_name,
                'raw_html': html_content,
                'file_path': str(html_file)
            }
            
            # Extract metadata from HTML comments
            lines = html_content.split('\n')
            for line in lines[:20]:  # Check first 20 lines
                if '<!--' in line:
                    for key in ['Scenario:', 'Lines:', 'Bundled:']:
                        if key in line:
                            value = line.split(':', 1)[-1].strip().strip('>')
                            scenario_data[key.lower().rstrip(':')] = value
            
            scenarios[scenario_name] = scenario_data
        
        return scenarios
    
    def _consolidate_results(self, all_results: Dict[str, Dict]) -> Dict[str, Any]:
        """Consolidate all carrier results into single JSON structure"""
        print("\n" + "="*80)
        print("📊 CONSOLIDATING RESULTS")
        print("="*80)
        
        consolidated = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'carriers': list(all_results.keys()),
                'total_carriers': len(all_results),
                'llm_extraction_skipped': self.skip_llm,
                'scraping_skipped': self.skip_scraping,
                'event_id': self.event_id
            },
            'carriers': {}
        }
        
        for carrier, result in all_results.items():
            if result.get('success'):
                scenarios = result.get('scenarios', {})
                # Check if LLM was actually skipped for this carrier
                llm_step = result.get('steps', {}).get('llm_extraction', {})
                llm_skipped = llm_step.get('skipped', False)
                
                consolidated['carriers'][carrier] = {
                    'success': True,
                    'scenarios': scenarios,
                    'scenario_count': len(scenarios),
                    'llm_extraction_skipped': llm_skipped
                }
                
                # Warn if file will be misleading
                if llm_skipped and scenarios:
                    print(f"  ⚠️  WARNING: {carrier} has scenarios data but LLM was skipped!")
            else:
                consolidated['carriers'][carrier] = {
                    'success': False,
                    'error': result.get('error', 'Unknown error')
                }
        
        return consolidated
    
    def _save_consolidated_output(self, consolidated: Dict[str, Any]):
        """Save consolidated JSON output"""
        # Don't create misleading file if LLM was skipped and no scenarios exist
        llm_skipped = consolidated.get('metadata', {}).get('llm_extraction_skipped', False)
        
        # Check if any carrier has actual scenarios data
        has_scenarios = False
        for carrier_data in consolidated.get('carriers', {}).values():
            if carrier_data.get('success') and carrier_data.get('scenarios'):
                has_scenarios = True
                break
        
        # If LLM was skipped and no scenarios, don't create misleading file
        if llm_skipped and not has_scenarios:
            print("\n⏭️  Skipping consolidated output file creation")
            print("   (LLM extraction was skipped, no extraction data to save)")
            print("   (Use --skip-llm=false to generate extraction data)")
            return
        
        timestamp = self.event_id
        
        # Modify filename to indicate if LLM was skipped
        if llm_skipped:
            filename = f"all_carriers_extraction_NO_LLM_{timestamp}.json"
            print("\n⚠️  WARNING: Creating file with 'NO_LLM' suffix - LLM extraction was skipped")
        else:
            filename = f"all_carriers_extraction_{timestamp}.json"
        
        output_path = self.output_base_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Consolidated output saved: {filename}")
        print(f"   Path: {output_path}")
    
    def _save_pipeline_log(self):
        """Save pipeline execution log"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.pipeline_dir / f"pipeline_log_{timestamp}.json"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(self.pipeline_log, f, indent=2, ensure_ascii=False)
        
        print(f"\n📋 Pipeline log saved: {log_file.name}")
    
    def _print_summary(self, all_results: Dict[str, Dict]):
        """Print final summary"""
        print("\n" + "="*80)
        print("📊 PIPELINE SUMMARY")
        print("="*80)
        
        for carrier, result in all_results.items():
            status = "✅" if result.get('success') else "❌"
            scenarios = result.get('scenarios', {})
            scenario_count = len(scenarios) if isinstance(scenarios, dict) else 0
            print(f"{status} {carrier.upper():10s} - {scenario_count} scenarios")
        
        print("="*80)

    def _annotate_file_with_event_id(self, file_path: Path):
        """Ensure stripped HTML files carry the current event ID comment."""
        try:
            if not file_path.exists():
                return
            marker = f"Extraction Event ID: {self.event_id}"
            header = f"<!-- {marker} -->"
            content = file_path.read_text(encoding='utf-8')
            if marker in content.splitlines()[0:5]:
                return
            file_path.write_text(f"{header}\n{content}", encoding='utf-8')
        except Exception:
            # Non-fatal; continue without blocking pipeline
            pass
    
    def _push_consolidated_to_github(self, consolidated_file: Path):
        """Automatically commit and push the consolidated file to GitHub."""
        import subprocess
        
        print("\n  📤 Auto-pushing consolidated file to GitHub...")
        
        try:
            # Check if git is available
            git_check = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True
            )
            if git_check.returncode != 0:
                print("  ⚠️  Git not available, skipping GitHub push")
                return
            
            # Check if we're in a git repository
            git_repo_check = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True
            )
            if git_repo_check.returncode != 0:
                print("  ⚠️  Not in a git repository, skipping GitHub push")
                return
            
            # Get the file path relative to repo root
            repo_root = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True,
                text=True
            ).stdout.strip()
            
            # Try both locations: data/consolidated/ and root
            file_to_add = None
            if consolidated_file.exists():
                # Try relative path first
                rel_path = consolidated_file.relative_to(Path.cwd())
                if (Path.cwd() / rel_path).exists():
                    file_to_add = str(rel_path)
                else:
                    # Try absolute path
                    file_to_add = str(consolidated_file)
            
            # Also check root directory for the same filename
            root_file = Path.cwd() / consolidated_file.name
            if root_file.exists() and root_file != consolidated_file:
                file_to_add = str(root_file)
            
            if not file_to_add:
                print(f"  ⚠️  Could not find consolidated file to add: {consolidated_file}")
                return
            
            # Add the file
            add_result = subprocess.run(
                ['git', 'add', file_to_add],
                capture_output=True,
                text=True
            )
            
            if add_result.returncode != 0:
                print(f"  ⚠️  Failed to add file to git: {add_result.stderr}")
                return
            
            # Commit
            commit_msg = f"Auto-update: Consolidated plans data ({self.event_id})"
            commit_result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                capture_output=True,
                text=True
            )
            
            if commit_result.returncode != 0:
                if "nothing to commit" in commit_result.stdout.lower():
                    print("  ℹ️  No changes to commit (file already up to date)")
                    return
                print(f"  ⚠️  Failed to commit: {commit_result.stderr}")
                return
            
            # Push to GitHub
            push_result = subprocess.run(
                ['git', 'push', 'origin', 'main'],
                capture_output=True,
                text=True
            )
            
            if push_result.returncode == 0:
                print(f"  ✅ Successfully pushed to GitHub!")
                print(f"     File: {file_to_add}")
                print(f"     Streamlit Cloud will auto-redeploy in 1-2 minutes")
            else:
                # Try 'master' branch if 'main' fails
                push_result = subprocess.run(
                    ['git', 'push', 'origin', 'master'],
                    capture_output=True,
                    text=True
                )
                if push_result.returncode == 0:
                    print(f"  ✅ Successfully pushed to GitHub (master branch)!")
                else:
                    print(f"  ⚠️  Failed to push to GitHub: {push_result.stderr}")
                    print(f"     You may need to push manually: git push origin main")
        
        except Exception as e:
            print(f"  ⚠️  Error during GitHub push: {e}")
            print(f"     You can manually push with: git add {consolidated_file.name} && git commit -m 'Update consolidated data' && git push")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Unified Multi-Carrier Pipeline')
    parser.add_argument('--carriers', nargs='+', 
                        choices=['telus', 'rogers', 'bell', 'freedom', 'koodo', 'fido', 'virgin'],
                        default=None, help='Carriers to process (default: all)')
    parser.add_argument('--skip-scraping', action='store_true',
                        help='Skip scraping step (use existing HTML)')
    parser.add_argument('--skip-llm', action='store_true',
                        help='Skip LLM extraction step')
    parser.add_argument('--llm-model', default='gpt-5-nano',
                        help='LLM model to use for extraction (default: gpt-5-nano)')
    parser.add_argument('--auto-push', action='store_true',
                        help='Automatically commit and push consolidated file to GitHub after pipeline completes')
    
    args = parser.parse_args()
    
    # Initialize and run pipeline
    pipeline = UnifiedPipeline(
        carriers=args.carriers,
        skip_scraping=args.skip_scraping,
        skip_llm=args.skip_llm,
        llm_model=args.llm_model,
        auto_push_to_github=args.auto_push
    )
    
    results = pipeline.run_complete_pipeline()
    
    print("\n✅ Pipeline complete!")
    return results


if __name__ == '__main__':
    main()
