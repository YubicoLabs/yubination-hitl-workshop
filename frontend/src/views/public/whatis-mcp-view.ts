import { LitElement, html, css, unsafeCSS } from 'lit';
import { customElement } from 'lit/decorators.js';
import landingStyles from '../../styles/landing.css?inline';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '../../components/app-header';
import '../../components/app-footer';
import { getBrandConfig } from '../../brand-config';

@customElement('whatis-mcp-view')
export class WhatIsMcpView extends LitElement {
  static styles = [
    css`
      ${unsafeCSS(landingStyles)}
      .content-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 4rem 1rem;
      }
      h1,
      h2 {
        font-weight: bold;
        margin-top: 2rem;
        margin-bottom: 1rem;
      }
      .lead {
        font-size: 1.25rem;
        font-weight: 300;
      }
      .feature-section {
        text-align: left;
      }
      ul {
        padding-left: 2rem;
      }
      li {
        margin-bottom: 0.5rem;
      }
      .text-center {
        text-align: center;
      }
      .my-5 {
        margin-top: 3rem;
        margin-bottom: 3rem;
      }
      .mt-5 {
        margin-top: 3rem;
      }
      .mb-5 {
        margin-bottom: 3rem;
      }
      p.lead {
        max-width: none;
      }
    `,
  ];

  render() {
    return html`
      <app-header></app-header>
      <main>
        <section class="feature-section main-section">
          <div class="section-container">
            <h2>Understanding the Model Context Protocol (MCP)</h2>
            <p class="lead mb-5">
              The Model Context Protocol (MCP) is an
              <a
                href="https://www.anthropic.com/news/model-context-protocol"
                target="_blank"
                rel="noopener noreferrer"
                >open standard developed by Anthropic</a
              >
              designed to revolutionize how AI assistants connect with the
              digital world. Think of it as a universal adapter, enabling AI to
              securely and intelligently interact with a vast array of
              applications, data sources, and software tools using a common
              language.
            </p>

            <h3>What is MCP and What Problem Does It Solve?</h3>
            <p>
              Historically, connecting AI models to external systems was a
              disjointed and often cumbersome task. Every new application or
              data repository necessitated a unique, custom-made integration.
              This resulted in capable AI models frequently operating in
              isolation, cut off from vital external information, thereby
              hindering the scalability of AI solutions and the development of
              genuinely interconnected intelligent platforms.
            </p>
            <p>
              MCP rectifies this by establishing a common, standardized
              communication pathway. It shifts from a model requiring numerous
              individual integrations—often visualized as an N×M problem, where
              N is the number of tools and M is the number of AI models—to a
              more streamlined, unified framework. This allows AI platforms to
              support a single protocol (MCP), and tool developers to make their
              applications accessible to any MCP-compliant AI by implementing an
              MCP server once.
            </p>
            <p>Fundamentally, MCP aims to overcome:</p>
            <ul>
              <li>
                <strong>Integration Fragmentation:</strong> It seeks to replace
                a multitude of bespoke, often fragile, connectors with a single,
                robust, and standardized protocol.
              </li>
              <li>
                <strong>Tool-to-Tool Language Mismatch:</strong> It offers a
                structured, self-describing interface. This means AI systems
                don't need to learn the unique API or command dialect of every
                individual tool. Instead, tools can announce their capabilities
                in a standard way, allowing AI to invoke them through more
                generalized instructions.
              </li>
              <li>
                <strong>Scalability Issues:</strong> By simplifying how new
                tools and AI models are connected, MCP fosters a more dynamic
                and easily expandable ecosystem for AI interactions.
              </li>
            </ul>

            <h3>How Does MCP Work? The Architecture</h3>
            <p>
              MCP functions using a client-server model, specifically adapted
              for communication between AI systems and software applications:
            </p>
            <ul>
              <li>
                <strong>MCP Servers:</strong> These function as adaptable
                intermediaries, operating in conjunction with a specific
                application or data service (like GitHub, Slack, a database, or
                ${getBrandConfig().name}). An MCP server is responsible for
                converting instructions, often phrased in natural language by an
                AI, into precise commands that the target application can
                execute. Key duties include:
                <ul>
                  <li>
                    <strong>Tool Discovery:</strong> Making the application's
                    available actions and capabilities known to AI clients.
                  </li>
                  <li>
                    <strong>Command Parsing:</strong> Translating AI-generated
                    instructions into exact application commands or API calls.
                  </li>
                  <li>
                    <strong>Response Formatting:</strong> Taking the output from
                    the application (such as data or confirmation messages) and
                    structuring it so the AI model can readily process it.
                  </li>
                  <li>
                    <strong>Error Handling:</strong> Intercepting issues like
                    invalid requests and providing informative error messages to
                    the AI, allowing for adjustments.
                  </li>
                </ul>
              </li>
              <li>
                <strong>MCP Clients:</strong> These are integral parts of an AI
                assistant or the platform it runs on (for instance, an
                AI-enhanced IDE or Anthropic's Claude Desktop app). The client
                establishes and maintains a connection with an MCP server. It
                manages the exchange of information (commonly using JSON-RPC 2.0
                messages) and delivers the server’s feedback to the AI model.
                This setup allows AI agents to dynamically find and utilize
                available MCP servers and their offered functionalities.
              </li>
            </ul>

            <h3>Key Goals and Features of MCP</h3>
            <ul>
              <li>
                <strong>Standardized Connectivity:</strong> Establishes a
                universal 'language' for AI to interface with a wide range of
                external systems and data sources.
              </li>
              <li>
                <strong>Enhanced Contextual Understanding:</strong> Permits AI
                models to obtain pertinent data from connected tools, leading to
                more accurate and situationally relevant outputs.
              </li>
              <li>
                <strong>Tool Usage and Action-Taking:</strong> Empowers AI not
                merely to process data, but to actively perform operations and
                initiate workflows within other software.
              </li>
              <li>
                <strong>Composable Workflows:</strong> Simplifies the creation
                of sophisticated, multi-step processes by enabling the chaining
                of capabilities from various MCP-enabled tools.
              </li>
              <li>
                <strong>Secure and Bi-directional Communication:</strong> Aims
                to ensure that the exchange of data between AI systems and
                external tools is conducted securely.
              </li>
              <li>
                <strong>Dynamic Discovery:</strong> Allows AI agents to
                automatically identify accessible MCP servers and the services
                they provide, without needing pre-configured, hard-coded
                integrations for each one.
              </li>
            </ul>

            <h3>
              MCP's Role in ${getBrandConfig().name} and its Significance for AI
              Agents
            </h3>
            <p>
              For ${getBrandConfig().name}, which itself functions as an MCP
              server for issue tracking systems, MCP is a cornerstone
              technology. It enables ${getBrandConfig().name} to integrate
              smoothly with a variety of AI agents and development tools. This
              integration facilitates several key advantages:
            </p>
            <ul>
              <li>
                <strong>Unified Issue Tracker Access:</strong> AI-driven coding
                assistants can leverage ${getBrandConfig().name} to communicate
                with diverse issue trackers like GitHub, Jira, and GitLab via a
                single, consistent MCP interface.
              </li>
              <li>
                <strong>AI-Powered Issue Management:</strong> Agents gain the
                ability to intelligently handle issues—such as creating new
                tickets, searching to prevent duplicates, updating statuses, and
                managing assignments—directly as part of their operational flow,
                utilizing ${getBrandConfig().name}'s specialized
                functionalities.
              </li>
              <li>
                <strong>Streamlined Developer Workflows:</strong> MCP allows AI
                to automate various development-related tasks, for example,
                linking code commits to their corresponding issues or updating
                an issue’s status based on the progress of development
                activities, all orchestrated through ${getBrandConfig().name}.
              </li>
            </ul>
            <p>
              More broadly, MCP serves as an essential integration fabric for AI
              agents, particularly vital for the "Action" component of their
              operational cycle. It furnishes the necessary 'plumbing' for these
              agents to interact effectively with the digital world, thereby
              making them more versatile, adaptable, and proficient in executing
              complex, multi-stage tasks across a multitude of different
              systems.
            </p>

            <h3>Getting Started with MCP</h3>
            <p>
              The MCP ecosystem is actively growing, driven by open-source
              collaboration. For developers looking to engage with MCP, several
              avenues are available:
            </p>
            <ul>
              <li>
                Familiarize themselves with the official MCP specification and
                Software Development Kits (SDKs), typically found on platforms
                like GitHub under the Model Context Protocol project.
              </li>
              <li>
                Leverage existing pre-built MCP servers for commonly used tools
                and systems. For instance,
                <strong
                  >${getBrandConfig().name} itself acts as an MCP server for
                  issue trackers</strong
                >, allowing AI agents to connect and manage tasks across
                platforms like GitHub, Jira, and GitLab through a standardized
                interface. Developers can explore integrating their AI tools
                with ${getBrandConfig().name}'s MCP server to enhance issue
                management capabilities.
              </li>
              <li>
                Integrate MCP servers with compatible AI-powered applications,
                such as Anthropic's Claude Desktop application, which supports
                local MCP server connections.
              </li>
              <li>
                Consult quickstart guides and documentation, often available on
                the official MCP website, to guide the development of custom MCP
                servers for other applications or data sources.
              </li>
            </ul>
            <p>
              MCP's advancement as a collaborative, open initiative encourages
              participation from developers, businesses, and AI pioneers to
              collectively shape the future of AI systems that possess deep
              contextual awareness.
            </p>

            <div class="text-center my-5">
              <sl-button
                variant="primary"
                size="large"
                href="/register"
                target="_blank"
                rel="noopener noreferrer"
                >Sign Up Now</sl-button
              >
            </div>

            <h3>Conclusion</h3>
            <p>
              The Model Context Protocol represents a significant step towards a
              more interconnected and capable AI landscape. By providing a
              common language for AI to interact with the digital world, MCP not
              only simplifies current integration challenges but also unlocks
              new possibilities for more intelligent, autonomous, and
              contextually aware AI applications. As the ecosystem around MCP
              continues to evolve, its impact on how we build and utilize
              AI-powered tools, including platforms like
              ${getBrandConfig().name}, will only continue to grow, paving the
              way for more seamless and powerful human-AI collaboration.
            </p>

            <div class="text-center mt-5">
              <sl-button variant="primary" outline href="/"
                >Back to Home</sl-button
              >
            </div>
          </div>
        </section>
      </main>
      <app-footer></app-footer>
    `;
  }
}
