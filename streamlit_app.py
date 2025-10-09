import streamlit as st
import os
import tempfile
from app.config import PipelineConfig, LLMConfig, VisionConfig, PlannerConfig
from scripts.run_pipeline import run_folder

st.set_page_config(layout="wide")

st.title("📄 LLM-Powered Document Pipeline")

# Sidebar for configuration
st.sidebar.header("⚙️ Configuration")

llm_provider = st.sidebar.selectbox("LLM Provider", ["gpt", "claude"], index=0)
llm_model = st.sidebar.text_input("Override Model ID (optional)")
vision_strategy = st.sidebar.selectbox("Vision Strategy", ["auto", "full_document", "page_by_page", "off"], index=0)
concurrency = st.sidebar.slider("Concurrency", 1, 10, 2)

# File uploader
uploaded_files = st.file_uploader("📂 Upload your documents", accept_multiple_files=True, type=None)

if uploaded_files:
    st.info(f"✅ {len(uploaded_files)} files uploaded.")
    
    if st.button("🚀 Run Pipeline"):
        with tempfile.TemporaryDirectory() as temp_dir:
            st.write(f"Created temporary directory: `{temp_dir}`")
            
            # Save uploaded files to the temporary directory
            for uploaded_file in uploaded_files:
                file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.write(f"Saved `{uploaded_file.name}` to temporary directory.")

            # Configure and run the pipeline
            with st.spinner("🧠 Running the pipeline... Please wait."):
                llm_enable_vision = vision_strategy in ["auto", "full_document", "page_by_page"]
                
                cfg = PipelineConfig(
                    llm=LLMConfig(provider=llm_provider, model=llm_model if llm_model else None, enable_vision=llm_enable_vision),
                    vision=VisionConfig(strategy=vision_strategy),
                    planner=PlannerConfig(concurrency=concurrency),
                )

                try:
                    results = run_folder(temp_dir, cfg)
                    
                    st.success("🎉 Pipeline finished successfully!")
                    
                    # Display results
                    st.subheader("📝 Results")
                    for result in results:
                        with st.expander(f"📄 {result.get('path', 'Unknown file')}"):
                            if "error" in result:
                                st.error(f"**Error:** {result['error']}")
                                st.code(result.get('trace', 'No traceback available.'))
                            else:
                                st.json(result)
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
                    st.exception(e)
else:
    st.info("Upload some documents to get started.")