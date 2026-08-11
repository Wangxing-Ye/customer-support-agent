import "./styles.css";
import { mountChatWidget } from "./widget/ChatApp.jsx";

const root = document.getElementById("widget-root");
if (root) {
  mountChatWidget(root);
}
