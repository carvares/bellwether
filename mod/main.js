// Starts the Bellwether widget one time when the Herdr app starts. It shows nothing.
import { View, div } from "gpui-kit";
import { appHome, checking, exec } from "herdr";

export default class BellwetherStart extends View {
  init() {
    // `herdr-app check` runs init() too. A check must not start the widget.
    if (checking()) return;
    // start.sh in this folder is a link to scripts/start.sh of the repository. It returns at once.
    // A second start does not open a second widget.
    exec(`${appHome()}/mods/bellwether/start.sh`, [])
      .then((result) => {
        if (result.code !== 0) console.log(`bellwether: start.sh failed with exit code ${result.code}`);
      })
      .catch(() => console.log("bellwether: start.sh did not run"));
  }

  render() {
    return div();
  }
}
