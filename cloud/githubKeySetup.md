ssh-keygen -t ed25519 -C "github-$(whoami)"
#set a password

eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519


ssh-add -l

cat ~/.ssh/id_ed25519.pub

#Add it in GitHub:
#Settings → SSH and GPG keys → New SSH key (paste it).


curl https://github.com/abhikchowdhury6.keys

to update ssh keys on remote machine
curl -fsSL https://github.com/abhikchowdhury6.keys >> ~/.ssh/authorized_keys
