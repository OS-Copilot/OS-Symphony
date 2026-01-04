export http_proxy=http://10.1.8.5:23128; 
export https_proxy=http://10.1.8.5:23128; 
export HTTP_PROXY=http://10.1.8.5:23128; 
export HTTPS_PROXY=http://10.1.8.5:23128; 
export no_proxy=localhost,127.0.0.1,10.140.52.51,172.17.0.0/16,20.20.20.0/24,0.0.0.0,10.140.60.25,.pjlab.org.cn; 
export NO_PROXY=localhost,127.0.0.1,10.140.52.51,172.17.0.0/16,20.20.20.0/24,0.0.0.0,10.140.60.25,.pjlab.org.cn;
EXP_NAME="xxx"
# enable_rewrite_instruction
python run_os_symphony.py \
  --provider_name "docker" \
  --path_to_vm "xxx" \
  --headless \
  --num_envs 1 \
  --max_steps 10 \
  --benchmark osworld \
  --domain "all" \
  --test_all_meta_path evaluation_examples/osworld/test_nogdrive.json \
  --result_dir "results" \
  --region "us-east-1" \
  --client_password "password" \
  --proxy "http://10.1.8.5:23128" \
  --tool_config mm_agents/os_symphony/tool/all_tool_config.yaml \
  --orchestrator_provider "openai" \
  --orchestrator_model "gpt-5" \
  --orchestrator_url "xxx" \
  --orchestrator_api_key "xxx" \
  --orchestrator_temperature 0.1 \
  --orchestrator_keep_first_image \
  --max_trajectory_length 8 \
  --grounder_provider "openai" \
  --grounder_model "ui-tars-1.5-7b" \
  --grounder_api_key "none" \
  --grounder_url "xxx" \
  --grounding_smart_resize \
  --grounding_width 1280 \
  --grounding_height 800 \
  --coder_provider "openai" \
  --coder_model "gpt-5" \
  --coder_url "xxx" \
  --coder_api_key "xxx" \
  --coder_temperature 0.1 \
  --coder_budget 20 \
  --memoryer_provider "openai" \
  --memoryer_model "gpt-5" \
  --memoryer_url "xxx" \
  --memoryer_api_key "xxx" \
  --memoryer_temperature 0.1 \
  --memoryer_max_images 8 \
  --searcher_provider "openai" \
  --searcher_model "gpt-5" \
  --searcher_url "xxx" \
  --searcher_api_key "xxx" \
  --searcher_temperature 0.1 \
  --searcher_type "vlm" \
  --searcher_engine "duckduckgo" \
  --searcher_budget 20\
  --searcher_screen_width 1920 \
  --searcher_screen_height 1080 \
  --searcher_path_to_vm "xxx" \
  --sleep_after_execution 3 \
  --exp_name ${EXP_NAME} \
  --enable_reflection 
