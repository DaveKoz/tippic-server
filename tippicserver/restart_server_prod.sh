export AWS_REGION='us-east-1'
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES # https://github.com/ansible/ansible/issues/32499

ansible-playbook playbooks/tippic-server-prod-restart-only.yml -i tippic-server-prod-1,tippic-server-prod-2 --extra-vars "tippic_prod_tg_arn='arn:aws:elasticloadbalancing:us-east-1:935522987944:targetgroup/tippic-prod/44e68fe465dd36c9'"
