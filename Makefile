PYTHON_CMD ?= $(shell if command -v /opt/homebrew/bin/python3 >/dev/null 2>&1 && /opt/homebrew/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then echo "/opt/homebrew/bin/python3"; else for cmd in python3 python3.13 python3.12 python3.11 python3.10; do if command -v $$cmd >/dev/null 2>&1 && $$cmd -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then echo $$cmd; exit 0; fi; done; echo "python3"; fi)

install: ## Install dependencies and request Spotify credentials
	@if ! command -v $(PYTHON_CMD) >/dev/null 2>&1 || ! $(PYTHON_CMD) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then \
		echo "⚠️  Python 3.10 or newer is required to install dependencies."; \
		if command -v $(PYTHON_CMD) >/dev/null 2>&1; then echo "Current version: $$($(PYTHON_CMD) --version)"; fi; \
		read -p "Would you like to attempt to install the latest Python now? [Y/n]: " install_python; \
		if [ "$$install_python" = "y" ] || [ "$$install_python" = "Y" ]; then \
			if command -v brew >/dev/null 2>&1; then \
				echo "📦 Installing Python via Homebrew..."; \
				brew install python3; \
			elif command -v apt-get >/dev/null 2>&1; then \
				echo "📦 Installing Python via apt..."; \
				sudo apt-get update || true; sudo apt-get install -y python3 python3-venv python-dev-is-python3 python3-pil cython3; \
				if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then \
					echo "⚠️  Your package manager only provided Python $$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo 'unknown')."; \
					read -p "Would you like to compile Python 3.11 from source? (This will take a few minutes) [Y/n]: " compile_python; \
					if [ "$$compile_python" = "y" ] || [ "$$compile_python" = "Y" ]; then \
						echo "📦 Installing build dependencies..."; \
						sudo apt-get update >/dev/null 2>&1 || true; \
						sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git >/dev/null 2>&1; \
						echo "📦 Downloading and compiling Python 3.11 (this may take a few minutes)..."; \
						wget -q https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz && \
						tar -xf Python-3.11.9.tgz && \
						cd Python-3.11.9 && ./configure --enable-optimizations --quiet >/dev/null && make -s -j 4 >/dev/null && sudo make -s altinstall >/dev/null && \
						cd .. && rm -rf Python-3.11.9 Python-3.11.9.tgz; \
						echo "✅ Python 3.11 compiled successfully."; \
					else \
						echo "❌ Installation aborted. Python 3.10+ is required."; \
						exit 1; \
					fi; \
				fi; \
			else \
				echo "❌ Could not determine package manager. Please install Python 3.10+ manually."; \
				exit 1; \
			fi; \
			echo "🔄 Please run \\033[1;36mmake\033[0m again."; \
			exit 1; \
		else \
			echo "❌ Installation aborted. Python 3.10+ is required."; \
			exit 1; \
		fi \
	fi
	$(PYTHON_CMD) -m venv .venv
	@if command -v apt-get >/dev/null 2>&1; then \
		PYTHON_VER=$$($(PYTHON_CMD) -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'); \
		echo "📦 Ensuring python$$PYTHON_VER-dev is installed..."; \
		sudo apt-get update >/dev/null 2>&1 || true; sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python$$PYTHON_VER-dev >/dev/null 2>&1 || true; \
	fi
	@echo "📦 Downloading Pillow C-headers for cross-version compatibility..."
	@mkdir -p .venv/include/Pillow
	@curl -sL https://github.com/python-pillow/Pillow/archive/refs/tags/10.3.0.tar.gz -o pillow.tar.gz
	@tar -xzf pillow.tar.gz
	@cp -r Pillow-10.3.0/src/libImaging/*.h .venv/include/Pillow/
	@rm -rf Pillow-10.3.0 pillow.tar.gz
	CFLAGS="-I$(CURDIR)/.venv/include/Pillow" .venv/bin/pip install -e .
	@rm -rf *.egg-info/
	@if [ ! -f config.ini ]; then cp config.ini.example config.ini; fi
	@if grep -q "client_id = <YOUR_CLIENT_ID_HERE>" config.ini; then \
		echo ""; \
		echo "Please provide your Spotify API credentials:"; \
		echo "You can obtain these from: https://developer.spotify.com/dashboard"; \
		echo ""; \
		read -p "Enter Spotify Client ID: " client_id; \
		read -p "Enter Spotify Client Secret: " client_secret; \
		echo ""; \
		echo "Optional: Provide your sp_dc cookie to fetch lyrics."; \
		echo "You can find it by following these instructions: https://github.com/akashrchandran/syrics/wiki/Finding-sp_dc"; \
		echo "Leave blank to skip for now."; \
		read -p "Enter sp_dc cookie (optional): " sp_dc; \
		sed "s/client_id = <YOUR_CLIENT_ID_HERE>/client_id = $$client_id/" config.ini > config.ini.tmp && mv config.ini.tmp config.ini; \
		sed "s/client_secret = <YOUR_CLIENT_SECRET_HERE>/client_secret = $$client_secret/" config.ini > config.ini.tmp && mv config.ini.tmp config.ini; \
		if [ -n "$$sp_dc" ]; then \
			sed "s|sp_dc = <YOUR SP_DC COOKIE FOR LYRICS>|sp_dc = $$sp_dc|" config.ini > config.ini.tmp && mv config.ini.tmp config.ini; \
		fi; \
	fi
	@echo ""
	@echo "✅ rpi-spotify-matrix-display successfully installed!"
	@echo ""
	@echo "🧮 To run on an pi-connected matrix: \033[1;36mmake run\033[0m"
	@echo "🖥️ To run within an emulator window: \033[1;36mmake emulate\033[0m"

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

clean: ## Reset repo to a clean state
	@echo "🧹 Resetting repo to a clean state...";
	rm -rf build/ dist/ *.egg-info/ .venv/
	rm -f .cache config.ini matrix.log
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || sudo rm -rf {} +
	find . -type f -name "*.pyc" -exec rm -f {} + 2>/dev/null || sudo rm -f {} +
	@if [ -f /etc/systemd/system/matrix.service ]; then \
		echo "🗑 Removing matrix systemd service..."; \
		sudo systemctl stop matrix || true; \
		sudo systemctl disable matrix || true; \
		sudo rm /etc/systemd/system/matrix.service; \
		sudo systemctl daemon-reload; \
	fi
	@if grep -q "alias matrix=" ~/.bash_aliases 2>/dev/null; then \
		echo "🗑 Removed 'matrix' alias from ~/.bash_aliases"; \
		sed "/alias matrix=/d" ~/.bash_aliases > ~/.bash_aliases.tmp && mv ~/.bash_aliases.tmp ~/.bash_aliases; \
	fi
	@echo "✅ Repo cleaned."

check-venv:
	@if [ ! -d .venv ]; then \
		echo "❌ Error: Virtual environment not found. Please run 'make' first."; \
		exit 1; \
	fi

emulate: check-venv ## Run the display within an emulator window
	.venv/bin/python main.py --emulate

## RASPBERRY PI SPECIFIC TARGETS ##

run: check-venv rpi-optimize rpi-service ## Run the display on a raspberry pi connected matrix
	@echo "▶️ Starting Spotify Matrix Display..."
	sudo .venv/bin/python main.py

check-rpi:
	@if [ ! -f /proc/device-tree/model ] || ! grep -qi "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then \
		echo "❌ Error: This command can only be run on a Raspberry Pi."; \
		exit 1; \
	fi

rpi-optimize: check-rpi ## Raspberry Pi ONLY - Optimize matrix performance
	@if [ ! -f /etc/systemd/system/matrix.service ] || [ "$(filter rpi-optimize,$(MAKECMDGOALS))" != "" ]; then \
		read -p "⚠️ Would you like to reserve a CPU core for the display and disable onboard audio to optimize performance? [Y/n]: " proceed; \
		if [ "$$proceed" != "y" ] && [ "$$proceed" != "Y" ]; then \
			echo "Optimization aborted. Feel free to use \\033[1;36mmake rpi-optimize\\033[0m to run this later."; \
		else \
			changed=0; \
			if ! grep -q "isolcpus=3" /boot/firmware/cmdline.txt; then \
				echo "⚙️  Adding isolcpus=3 to /boot/firmware/cmdline.txt..."; \
				sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.tmp; \
				sudo sed -i 's/$$/ isolcpus=3/' /boot/firmware/cmdline.txt.tmp; \
				sudo mv /boot/firmware/cmdline.txt.tmp /boot/firmware/cmdline.txt; \
				echo "✅ isolcpus=3 added."; \
				changed=1; \
			fi; \
			if ! grep -q "^blacklist snd_bcm2835" /etc/modprobe.d/alsa-blacklist.conf 2>/dev/null; then \
				echo "⚙️  Blacklisting onboard audio (snd_bcm2835)..."; \
				echo "blacklist snd_bcm2835" | sudo tee -a /etc/modprobe.d/alsa-blacklist.conf > /dev/null; \
				echo "✅ snd_bcm2835 blacklisted."; \
				changed=1; \
			fi; \
			if ! grep -q "^dtparam=audio=off" /boot/firmware/config.txt; then \
				echo "⚙️  Disabling onboard audio in config.txt..."; \
				sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' /boot/firmware/config.txt || true; \
				if ! grep -q "^dtparam=audio=off" /boot/firmware/config.txt; then \
					echo "dtparam=audio=off" | sudo tee -a /boot/firmware/config.txt > /dev/null; \
				fi; \
				echo "✅ Onboard audio disabled."; \
				changed=1; \
			fi; \
			if [ $$changed -eq 1 ]; then \
				echo "🔄 Please reboot your Raspberry Pi for changes to take effect."; \
				echo "Note: You must run \033[1;36mmake run\033[0m after reboot to complete Spotify authorization!"; \
				echo ""; \
				read -p "Reboot now? [Y/n]: " ans; \
				if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
					echo "Rebooting..."; \
					sudo reboot; \
				else \
					echo "Reboot skipped. Remember to reboot manually later."; \
				fi; \
				exit 1; \
			fi; \
		fi; \
	fi

rpi-service: check-rpi ## Raspberry Pi ONLY - Set up systemd service and alias
	@if [ ! -f /etc/systemd/system/matrix.service ]; then \
		echo "⚙️ Installing systemd service to automatically run display at startup..."; \
		sed "s|__WORKING_DIR__|$(CURDIR)|g" matrix.service | sudo tee /etc/systemd/system/matrix.service > /dev/null; \
		echo "🔄 Reloading systemd..."; \
		sudo systemctl daemon-reload; \
		echo "🎉 Matrix service installed! This can be used after Spotify authorization is complete."; \
	fi
	@if ! grep -q "alias matrix=" ~/.bash_aliases 2>/dev/null; then \
		echo "⚡ Adding alias 'matrix' to ~/.bash_aliases..."; \
		echo "alias matrix='sudo service matrix'" >> ~/.bash_aliases; \
		. ~/.bash_aliases; \
		echo "✅ Done!"; \
		echo ""; \
	fi