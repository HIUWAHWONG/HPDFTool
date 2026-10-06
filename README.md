# HPDFTool Pro - Professional Offline PDF Toolkit

**HPDFTool Pro** is a modern, full-featured, and completely offline desktop PDF utility built with Python and Tkinter. Designed for maximum productivity, it is entirely **ad-free** and processes all data strictly on your local machine to guarantee data privacy. 

Its standout core feature is its **In-place Text Editor**, powered by PyMuPDF. Unlike standard PDF tools that only overlay text, HPDFTool Pro extracts exact character coordinates, font sizes, scales, colors, and background attributes, allowing you to click directly on the PDF layout and modify text while preserving images and vector graphics natively.

---

## 🚀 Key Features

The workspace uses a streamlined "Sidebar + Interactive Canvas" interface to bundle 6 heavy-duty PDF production utilities:

1. **📝 Advanced In-place Text Editor**
   * **True Text Replacement**: Click any text box directly on the rendering canvas to rewrite content in its original position. 
   * **Flexible Granularity Modes**: Choose between parsing your document text by **Line**, **Span**, or **Paragraph** block layouts to control your editing boundary.
   * **Layout Intelligence**: Toggle "Auto-shrink long text" to auto-scale fonts and prevent overflows, or enable "Cover text on image backgrounds" to smoothly wipe away original text using dynamic background color sampling.
   * **Global Find & Replace**: Execute case-sensitive regex find-and-replace queries across the entire document page range at once.

2. **📋 Streamlined Text Selection & Copy**
   * Drag to lasso any custom coordinate area or simply click a single block to select whole flowing paragraphs.
   * Features a "Merge paragraph line breaks" toggle to completely strip away messy hard returns from original PDF column wraps when copying.
   * Auto-copy directly to clipboard upon selection.

3. **🔀 PDF Merger**
   * Queue multiple PDF files with an interactive ordering list.
   * Easily shift files up or down, delete selections, or wipe the queue cleanly.
   * Includes automated runtime authentication hooks to merge password-protected files flawlessly.

4. **✂️ PDF Splitter & Extractor**
   * Parse non-sequential pages using logical string ranges (e.g., `1-3, 5, 8-`), featuring automatic open-ended handling up to the final page count.
   * Extract target pages into a unified standalone PDF, or break every page down into separate individual documents simultaneously.

5. **🎨 Dynamic Watermark Tool**
   * Inject high-fidelity text watermarks across the document with strict runtime parameters (Text, Font Size, Scale Angle, Opacity, and Grid Tiling).
   * Built with a multi-threaded reactive canvas view that updates instantly as you tweak sliders to test color schemes before commitment.

6. **🖼️ Pages to Images Exporter**
   * Convert complete PDF page layouts into clean image files without stripping text elements away.
   * Supports custom distribution resolutions ranging from **72 DPI** to sharp **400 DPI** profiles in pure **PNG** or **JPG** formats.

7. **🔒 System Security & Encryption**
   * **AES-256 Bit Encryption**: Secure open files instantly by generating strong User and Owner security pass-keys.
   * **One-Click Security Removal**: Input a valid password to strip existing restrictions and export a pure, unrestricted PDF file copy.

---

## 🛠️ Technology Stack

* **Language**: Python 3.9+
* **UI Framework**: Tkinter / Ttk (Integrated with native Windows `shcore` Process DPI Awareness to ensure pixel-perfect, crisp rendering on high-resolution displays).
* **Core PDF Engine**: `PyMuPDF` (`fitz`)
* **Imaging Layer**: `Pillow` (`PIL`)

---

## 📦 Getting Started & Running Locally

### 1. Clone the Repository
```bash
git clone https://github.com
cd HPDFTool
```

### 2. Install Project Dependencies
Run the following pip command in your terminal to grab required underlying libraries:
```bash
pip install pymupdf pillow
```

### 3. Launch the Application
```bash
python HPDFTool.py
```

### ⌨️ Global Hotkeys
* `Ctrl + O` : Open file dialog to load a new PDF document.
* `Ctrl + S` : Trigger incremental save-as export for pending text adjustments.
* `Ctrl + Z` : Undo the last uncommitted text manipulation block instantly.

---

## 🔨 One-Click Windows Executable (.exe) Compilation

The repository includes a highly optimized build automation script `build_exe.bat`. You **do not** need PyInstaller or dependencies installed in your global system environment to bundle the app.

### Packaging Instructions:
1. **(Optional) Add Icon**: Place a custom file named `app.ico` in the same directory as `build_exe.bat` to automatically map it as your application's desktop icon.
2. **Double-Click to Build**: Simply double-click `build_exe.bat` inside Windows Explorer.

### Automated Sandbox Workflow Breakdown:
* **Environment Check**: Verifies Python environment variable availability (Python 3.9+).
* **Isolated Sandbox Environment**: The batch script spins up an isolated Python Virtual Environment (`.venv_build`). This ensures that only target dependencies are downloaded and compiled, preventing heavy, unrelated global Python packages from bloating your deployment package.
* **Clean Build Pipeline**: Automatically upgrades `pip`, fetches secure copies of `pymupdf`, `pillow`, and `pyinstaller` silently, and runs the compilation.
* **Distribution Output**: Uses the `--noconsole` hidden-terminal framework to deliver a single standalone runtime execution bundle under `dist\HPDFTool.exe`. It automatically fires up a native File Explorer window focusing on the distribution file upon success.
