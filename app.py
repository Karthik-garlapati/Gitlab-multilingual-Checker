import streamlit as st
import os
import tempfile
import subprocess
import json
import re
from pathlib import Path
from typing import Dict, List, Set
import requests
import zipfile
import shutil

# Page configuration
st.set_page_config(
    page_title="Streamlit Multilingual Checker - English & Indic Languages",
    page_icon="🌍",
    layout="wide"
)

def clone_gitlab_repo(repo_url: str, temp_dir: str) -> bool:
    """Clone GitLab repository to temporary directory using multiple methods"""
    try:
        # Method 1: Try git clone first
        if not repo_url.endswith('.git'):
            git_url = repo_url + '.git'
        else:
            git_url = repo_url
        
        try:
            result = subprocess.run(
                ['git', 'clone', git_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        # Method 2: Try downloading as ZIP file
        try:
            # Convert GitLab URL to archive download URL (works for any GitLab instance)
            if '//' in repo_url and ('gitlab' in repo_url.lower() or 'git' in repo_url.lower()):
                # Extract components from URL
                parts = repo_url.rstrip('/').split('/')
                if len(parts) >= 2:
                    # Get the base domain and path
                    protocol_and_domain = '/'.join(parts[:-2])  # https://code.swecha.org
                    owner = parts[-2]  # soai2025/soai-hackathon  
                    repo = parts[-1]   # arogya-lens
                    
                    if repo.endswith('.git'):
                        repo = repo[:-4]
                    
                    # Try different archive URL patterns for different GitLab instances
                    possible_urls = [
                        f"{protocol_and_domain}/{owner}/{repo}/-/archive/main/{repo}-main.zip",
                        f"{protocol_and_domain}/{owner}/{repo}/-/archive/master/{repo}-master.zip",
                        f"{protocol_and_domain}/{owner}/{repo}/repository/archive.zip?ref=main",
                        f"{protocol_and_domain}/{owner}/{repo}/repository/archive.zip?ref=master"
                    ]
                    
                    for zip_url in possible_urls:
                        try:
                            response = requests.get(zip_url, timeout=30)
                            if response.status_code == 200:
                                zip_path = os.path.join(temp_dir, 'repo.zip')
                                with open(zip_path, 'wb') as f:
                                    f.write(response.content)
                                
                                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                    zip_ref.extractall(temp_dir)
                                
                                # Move extracted content to temp_dir root
                                extracted_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
                                if extracted_dirs:
                                    extracted_path = os.path.join(temp_dir, extracted_dirs[0])
                                    for item in os.listdir(extracted_path):
                                        shutil.move(os.path.join(extracted_path, item), temp_dir)
                                    os.rmdir(extracted_path)
                                
                                os.remove(zip_path)
                                return True
                        except Exception:
                            continue
        except Exception:
            pass
        
        return False
        
    except Exception as e:
        st.error(f"Error accessing repository: {str(e)}")
        return False

def find_streamlit_files(directory: str) -> List[Path]:
    """Find all Python files that might be Streamlit applications"""
    streamlit_files = []
    
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and common non-source directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['_pycache_', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if 'streamlit' in content.lower() or 'st.' in content:
                            streamlit_files.append(file_path)
                except Exception:
                    continue
    
    return streamlit_files

def analyze_i18n_patterns(file_path: Path) -> Dict:
    """Analyze a file for internationalization patterns"""
    patterns = {
        'gettext': {
            'imports': [r'import\s+gettext', r'from\s+gettext\s+import'],
            'functions': [r'_\(', r'gettext\(', r'ngettext\('],
            'setup': [r'gettext\..\(.\)', r'\.bindtextdomain\(', r'\.textdomain\(']
        },
        'streamlit_i18n': {
            'imports': [r'import\s+streamlit_i18n', r'from\s+streamlit_i18n'],
            'functions': [r'i18n\(', r'\.translate\(', r'\.t\(']
        },
        'babel': {
            'imports': [r'import\s+babel', r'from\s+babel'],
            'functions': [r'Locale\(', r'format_currency\(', r'format_date\(']
        },
        'custom_translation': {
            'dictionaries': [r'translations\s*=\s*{', r'languages\s*=\s*{', r'TRANSLATIONS\s*='],
            'functions': [r'translate\(', r'get_text\(', r'tr\(']
        },
        'language_detection': {
            'patterns': [r'st\.selectbox.*lang', r'language.*select', r'locale', r'LANG']
        }
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return {}
    
    results = {}
    
    for category, pattern_dict in patterns.items():
        category_results = {}
        for pattern_type, pattern_list in pattern_dict.items():
            matches = []
            for pattern in pattern_list:
                found = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                if found:
                    matches.extend(found)
            if matches:
                category_results[pattern_type] = matches
        if category_results:
            results[category] = category_results
    
    return results

def find_translation_files(directory: str) -> Dict[str, List[Path]]:
    """Find translation-related files"""
    translation_files = {
        'po_files': [],
        'mo_files': [],
        'json_translations': [],
        'yaml_translations': [],
        'properties_files': []
    }
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            file_path = Path(root) / file
            
            if file.endswith('.po'):
                translation_files['po_files'].append(file_path)
            elif file.endswith('.mo'):
                translation_files['mo_files'].append(file_path)
            elif file.endswith('.json') and any(keyword in file.lower() for keyword in ['lang', 'translation', 'locale', 'i18n']):
                translation_files['json_translations'].append(file_path)
            elif file.endswith(('.yml', '.yaml')) and any(keyword in file.lower() for keyword in ['lang', 'translation', 'locale', 'i18n']):
                translation_files['yaml_translations'].append(file_path)
            elif file.endswith('.properties'):
                translation_files['properties_files'].append(file_path)
    
    return translation_files

def detect_languages_in_content(content: str) -> Set[str]:
    """Detect potential languages in text content - English and Indic languages only"""
    # Language detection focused on English and Indic languages
    language_indicators = {
        'english': ['en', 'english', 'hello', 'thank you', 'please', 'welcome', 'goodbye'],
        'hindi': ['hi', 'हिंदी', 'नमस्ते', 'धन्यवाद', 'कृपया', 'स्वागत', 'अलविदा'],
        'bengali': ['bn', 'বাংলা', 'নমস্কার', 'ধন্যবাদ', 'দয়া করে', 'স্বাগতম'],
        'tamil': ['ta', 'தமிழ்', 'வணக்கம்', 'நன்றி', 'தயவுசெய்து', 'வரவேற்கிறோம்'],
        'telugu': ['te', 'తెలుగు', 'నమస్కారం', 'ధన్యవాదాలు', 'దయచేసి', 'స్వాగతం'],
        'marathi': ['mr', 'मराठी', 'नमस्कार', 'धन्यवाद', 'कृपया', 'स्वागत'],
        'gujarati': ['gu', 'ગુજરાતી', 'નમસ્તે', 'આભાર', 'કૃપા કરીને', 'સ્વાગત'],
        'kannada': ['kn', 'ಕನ್ನಡ', 'ನಮಸ್ತೆ', 'ಧನ್ಯವಾದಗಳು', 'ದಯವಿಟ್ಟು', 'ಸ್ವಾಗತ'],
        'malayalam': ['ml', 'മലയാളം', 'നമസ്തേ', 'നന്ദി', 'ദയവായി', 'സ്വാഗതം'],
        'punjabi': ['pa', 'ਪੰਜਾਬੀ', 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ', 'ਧੰਨਵਾਦ', 'ਕਿਰਪਾ ਕਰਕੇ'],
        'oriya': ['or', 'ଓଡ଼ିଆ', 'ନମସ୍କାର', 'ଧନ୍ୟବାଦ', 'ଦୟାକରି', 'ସ୍ୱାଗତ'],
        'assamese': ['as', 'অসমীয়া', 'নমস্কাৰ', 'ধন্যবাদ', 'অনুগ্ৰহ কৰি'],
        'urdu': ['ur', 'اردو', 'آداب', 'شکریہ', 'براہ کرم', 'خوش آمدید'],
        'sanskrit': ['sa', 'संस्कृत', 'नमस्ते', 'धन्यवाद', 'कृपया'],
        'kashmiri': ['ks', 'कॉशुर', 'नमस्कार', 'शुक्रिया', 'मेहरबानी'],
        'nepali': ['ne', 'नेपाली', 'नमस्ते', 'धन्यवाद', 'कृपया', 'स्वागत'],
        'sinhala': ['si', 'සිංහල', 'ආයුබෝවන්', 'ස්තූතියි', 'කරුණාකර']
    }
    
    detected_languages = set()
    content_lower = content.lower()
    
    for lang, indicators in language_indicators.items():
        if any(indicator in content_lower for indicator in indicators):
            detected_languages.add(lang)
    
    return detected_languages

def analyze_requirements_file(directory: str) -> Dict:
    """Analyze requirements files for i18n-related packages"""
    i18n_packages = [
        'streamlit-i18n', 'babel', 'gettext', 'python-gettext',
        'flask-babel', 'django-rosetta', 'polib', 'translate'
    ]
    
    found_packages = []
    requirements_files = []
    
    for req_file in ['requirements.txt', 'requirements.in', 'pyproject.toml', 'setup.py', 'Pipfile']:
        req_path = Path(directory) / req_file
        if req_path.exists():
            requirements_files.append(req_file)
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for package in i18n_packages:
                        if package.lower() in content.lower():
                            found_packages.append(package)
            except Exception:
                continue
    
    return {
        'requirements_files': requirements_files,
        'i18n_packages': found_packages
    }

def generate_multilingual_report(directory: str) -> Dict:
    """Generate comprehensive multilingual analysis report"""
    report = {
        'is_multilingual': False,
        'confidence_score': 0,
        'streamlit_files': [],
        'i18n_patterns': {},
        'translation_files': {},
        'detected_languages': set(),
        'requirements_analysis': {},
        'recommendations': []
    }
    
    # Find Streamlit files
    streamlit_files = find_streamlit_files(directory)
    report['streamlit_files'] = [str(f.relative_to(directory)) for f in streamlit_files]
    
    # Analyze each Streamlit file for i18n patterns
    all_patterns = {}
    all_languages = set()
    
    for file_path in streamlit_files:
        patterns = analyze_i18n_patterns(file_path)
        if patterns:
            all_patterns[str(file_path.relative_to(directory))] = patterns
        
        # Check for languages in content
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                languages = detect_languages_in_content(content)
                all_languages.update(languages)
        except Exception:
            continue
    
    report['i18n_patterns'] = all_patterns
    report['detected_languages'] = all_languages
    
    # Find translation files
    translation_files = find_translation_files(directory)
    report['translation_files'] = {k: [str(Path(f).relative_to(directory)) for f in v] 
                                  for k, v in translation_files.items()}
    
    # Analyze requirements
    requirements_analysis = analyze_requirements_file(directory)
    report['requirements_analysis'] = requirements_analysis
    
    # Calculate confidence score and determine if multilingual
    score = 0
    
    if all_patterns:
        score += 40  # Strong indicator
    if any(translation_files.values()):
        score += 30  # Translation files present
    if requirements_analysis['i18n_packages']:
        score += 20  # I18n packages in requirements
    if len(all_languages) > 1:
        score += 10  # Multiple languages detected
    
    report['confidence_score'] = min(score, 100)
    report['is_multilingual'] = score >= 30
    
    # Generate recommendations
    recommendations = []
    if not report['is_multilingual']:
        recommendations.append("Consider implementing internationalization for English and Indic languages using libraries like streamlit-i18n or gettext")
        recommendations.append("Add language selection widget with English and Indic language options")
        recommendations.append("Create translation files for target Indic languages (Hindi, Bengali, Tamil, etc.)")
        recommendations.append("Consider using Unicode fonts that support Indic scripts")
    else:
        if not requirements_analysis['i18n_packages']:
            recommendations.append("Document your i18n dependencies in requirements.txt")
        if not any(translation_files.values()):
            recommendations.append("Consider using standard translation file formats (.po, .json) for Indic languages")
        recommendations.append("Ensure proper Unicode support for Indic scripts in your application")
        recommendations.append("Test your application with different Indic language inputs")
    
    report['recommendations'] = recommendations
    
    return report

# Streamlit UI
def main():
    st.title("🌍 Streamlit Multilingual Checker - English & Indic Languages")
    st.markdown("Analyze your Streamlit application to check if it supports English and Indic languages")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        st.info("Enter your Git repository URL to analyze its multilingual capabilities for English and Indic languages")
        
        # Language scope information
        st.markdown("### Supported Language Detection")
        st.markdown("""
        **English:**
        - English
        
        **Indic Languages:**
        - Hindi (हिंदी)
        - Bengali (বাংলা)
        - Tamil (தமிழ்)
        - Telugu (తెలుగు)
        - Marathi (मराठी)
        - Gujarati (ગુજરાતી)
        - Kannada (ಕನ್ನಡ)
        - Malayalam (മലയാളം)
        - Punjabi (ਪੰਜਾਬੀ)
        - Oriya (ଓଡ଼ିଆ)
        - Assamese (অসমীয়া)
        - Urdu (اردو)
        - Sanskrit (संस्कृत)
        - Kashmiri (कॉशुर)
        - Nepali (नेपाली)
        - Sinhala (සිංහල)
        """)
    
    # Main interface
    repo_url = st.text_input(
        "Git Repository URL",
        placeholder="https://gitlab.com/username/repository or https://code.swecha.org/username/repository",
        help="Enter the full Git repository URL (must be public)"
    )
    
    # URL validation
    if repo_url and not repo_url.startswith(('http://', 'https://')):
        st.warning("⚠️ Please enter a complete URL starting with http:// or https://")
    
    if repo_url and repo_url.startswith(('http://', 'https://')):
        if st.button("Analyze Repository", type="primary"):
            with st.spinner("Downloading repository and analyzing..."):
                # Create temporary directory
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Clone repository
                    st.info("📥 Downloading repository... This may take a moment.")
                    if clone_gitlab_repo(repo_url, temp_dir):
                        st.success("✅ Repository downloaded successfully!")
                        
                        # Generate report
                        st.info("🔍 Analyzing files for multilingual patterns...")
                        report = generate_multilingual_report(temp_dir)
                        
                        # Display results
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.metric(
                                "Multilingual Status",
                                "✅ Yes" if report['is_multilingual'] else "❌ No"
                            )
                        
                        with col2:
                            st.metric(
                                "Streamlit Files Found",
                                len(report['streamlit_files'])
                            )
                        
                        # Detailed Analysis
                        st.header("📊 Detailed Analysis")
                        
                        # Translation Files
                        translation_found = any(report['translation_files'].values())
                        if translation_found:
                            with st.expander("📄 Translation Files"):
                                for file_type, files in report['translation_files'].items():
                                    if files:
                                        st.write(f"{file_type.replace('_', ' ').title()}:")
                                        for file in files:
                                            st.code(file, language='text')
                        
                        # Requirements Analysis
                        if report['requirements_analysis']['i18n_packages']:
                            with st.expander("📦 I18n Packages in Requirements"):
                                for package in report['requirements_analysis']['i18n_packages']:
                                    st.code(package)
                        
                        # Recommendations
                        if report['recommendations']:
                            st.header("💡 Recommendations")
                            for i, rec in enumerate(report['recommendations'], 1):
                                st.write(f"{i}. {rec}")
                        
                        # Summary
                        st.header("📋 Summary")
                        
                        if report['is_multilingual']:
                            st.success("✅ This Streamlit application appears to have multilingual support for English and/or Indic languages!")
                            st.balloons()
                        else:
                            st.warning("⚠ This Streamlit application does not appear to have multilingual support for English and Indic languages.")
                        
                        # Export report
                        if st.button("📥 Download Report as JSON"):
                            # Convert sets to lists for JSON serialization
                            export_report = report.copy()
                            export_report['detected_languages'] = list(report['detected_languages'])
                            
                            st.download_button(
                                label="Download JSON Report",
                                data=json.dumps(export_report, indent=2),
                                file_name=f"multilingual_report_{repo_url.split('/')[-1]}.json",
                                mime="application/json"
                            )
                    
                    else:
                        st.error("❌ Failed to download repository. Please check:")
                        st.markdown("""
                        - **URL is correct** and publicly accessible
                        - **Repository exists** and is not private
                        - **Network connection** is stable
                        - Try copying the exact URL from your browser
                        """)
                        
                        st.info("💡 **Tip:** Make sure the GitLab repository is public or use a repository you have access to.")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "*Note:* This tool analyzes code patterns and files to detect multilingual support "
        "specifically for English and Indic languages. It may not catch all custom "
        "implementations of internationalization."
    )

if __name__ == "__main__":
    main()
